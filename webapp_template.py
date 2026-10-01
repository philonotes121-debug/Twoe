SECTION_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__SECTION_TITLE__</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  :root {
    --bg: var(--tg-theme-bg-color, #FFF3F8);
    --text: var(--tg-theme-text-color, #3A2233);
    --hint: var(--tg-theme-hint-color, #9C7C93);
    --accent: #E85D9C;
    --accent-soft: #FBDCEA;
    --card-bg: var(--tg-theme-secondary-bg-color, #FFFFFF);
    --success: #6FB98F;
  }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 16px; background: var(--bg); background-image: radial-gradient(circle at 100% 0%, #FDEBF5 0%, transparent 40%); color: var(--text); font-family: -apple-system, "Segoe UI", Roboto, sans-serif; }
  header { text-align: center; margin-bottom: 14px; }
  header h1 { font-size: 19px; margin: 4px 0; }
  header p { color: var(--hint); font-size: 13px; margin: 0; }
  .search-bar { display: flex; gap: 8px; margin-bottom: 14px; }
  .search-bar input { flex: 1; padding: 10px 14px; border-radius: 14px; border: 1px solid var(--accent-soft); background: var(--card-bg); color: var(--text); font-size: 14px; outline: none; }
  .filters { display: flex; gap: 6px; margin-bottom: 14px; flex-wrap: wrap; }
  .chip { padding: 6px 12px; border-radius: 999px; background: var(--accent-soft); color: var(--accent); font-size: 12px; cursor: pointer; border: 1px solid transparent; user-select: none; }
  .chip.active { background: var(--accent); color: #fff; }
  .card { background: var(--card-bg); border-radius: 16px; padding: 14px; margin-bottom: 10px; box-shadow: 0 1px 6px rgba(232,93,156,0.10); border: 1px solid rgba(232,93,156,0.08); }
  .card-title { font-size: 15px; font-weight: 600; margin: 0 0 4px 0; }
  .card-row { font-size: 12.5px; color: var(--hint); margin: 2px 0; }
  .card-row b { color: var(--text); }
  .card-footer { display: flex; align-items: center; justify-content: space-between; margin-top: 10px; }
  .price { font-weight: 700; color: var(--accent); font-size: 14.5px; }
  .price.tbd { color: var(--accent); font-weight: 600; font-size: 12.5px; }
  .buy-btn { background: var(--accent); color: #fff; border: none; padding: 8px 16px; border-radius: 12px; font-size: 13px; font-weight: 600; cursor: pointer; }
  .buy-btn:disabled { background: var(--hint); }
  .urgency { display: inline-block; margin-top: 6px; font-size: 11px; font-weight: 700; color: #D64545; background: #FDE4E4; padding: 3px 9px; border-radius: 999px; }
  .empty { text-align: center; color: var(--hint); padding: 40px 10px; font-size: 14px; }
  .trust-badge { text-align: center; font-size: 11.5px; color: var(--success); margin-top: 18px; padding-bottom: 10px; }
</style>
</head>
<body>

<header>
  <h1>📚 __SECTION_TITLE__</h1>
  <p>__TAGLINE__</p>
</header>

<div class="search-bar">
  <input id="searchInput" type="text" placeholder="🔍 Search course or faculty...">
</div>

<div class="filters" id="mediumFilters">
  <div class="chip active" data-medium="all">All</div>
  <div class="chip" data-medium="english">English</div>
  <div class="chip" data-medium="hindi">Hindi</div>
</div>

<div id="courseList"></div>
<div id="emptyState" class="empty" style="display:none;">😕 No courses found. Try a different search.</div>

<div class="trust-badge">🔒 Verified courses • Curated by Professor</div>

<script>
  const tg = window.Telegram.WebApp;
  tg.ready();
  tg.expand();

  const SECTION_KEY = "__SECTION_KEY__";
  let allCourses = [];
  let activeMedium = "all";

  async function loadCourses() {
    const res = await fetch(`/api/courses?section_key=${SECTION_KEY}`, {headers: {"X-Init-Data": tg.initData || ""}});
    if (res.status === 403) {
      document.getElementById("courseList").innerHTML = '<div class="empty">🔒 Access required.<br>Send /start in the bot and tap Request Access.</div>';
      return;
    }
    allCourses = await res.json();
    render();
  }

  function render() {
    const q = document.getElementById("searchInput").value.trim().toLowerCase();
    const list = document.getElementById("courseList");
    const empty = document.getElementById("emptyState");
    list.innerHTML = "";

    const filtered = allCourses.filter(c => {
      const mediumOk = activeMedium === "all" || (c.medium || "").toLowerCase().includes(activeMedium);
      const searchOk = !q || c.name.toLowerCase().includes(q) || (c.faculty || "").toLowerCase().includes(q);
      return mediumOk && searchOk;
    });

    if (filtered.length === 0) { empty.style.display = "block"; return; }
    empty.style.display = "none";

    for (const c of filtered) {
      const card = document.createElement("div");
      card.className = "card";
      const priceHtml = c.price !== null
        ? `<span class="price">₹${c.price}</span>`
        : `<span class="price tbd">Price on request</span>`;
      // Buying is always allowed — even while a price is still being finalized,
      // Professor confirms the exact amount when the order comes in.
      const buyBtn = `<button class="buy-btn" onclick="buyCourse(${c.id})">Buy Now</button>`;
      const urgencyPool = ["🔥 Only 2 left!", "🔥 Only 3 left!", "⚡ Hurry, few seats left!", "🔥 Last 2 seats!"];
      const urgency = urgencyPool[(c.id + Math.floor(Date.now() / 3600000)) % urgencyPool.length];
      card.innerHTML = `
        <div class="card-title">${c.name}</div>
        <div class="card-row">👨‍🏫 <b>${c.faculty || "—"}</b></div>
        <div class="card-row">🌐 ${c.medium || "—"}</div>
        <div class="card-row">📝 ${c.notes || "Complete course, lifetime access"}</div>
        <div><span class="urgency">${urgency}</span></div>
        <div class="card-footer">${priceHtml}${buyBtn}</div>
      `;
      list.appendChild(card);
    }
  }

  const BOT_USERNAME = "__BOT_USERNAME__";

  function buyCourse(courseId) {
    // NOTE: tg.sendData() only works for Mini Apps launched from a
    // *keyboard* button — this catalog opens from an *inline* button, so
    // sendData is silently ignored by Telegram. A start-parameter deep link
    // is the reliable way to hand the course back to the bot from here.
    if (BOT_USERNAME) {
      tg.openTelegramLink(`https://t.me/${BOT_USERNAME}?start=buy_${courseId}`);
    }
    tg.close();
  }

  document.getElementById("searchInput").addEventListener("input", render);
  document.querySelectorAll(".chip").forEach(chip => {
    chip.addEventListener("click", () => {
      document.querySelectorAll(".chip").forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      activeMedium = chip.dataset.medium;
      render();
    });
  });

  loadCourses();
</script>
</body>
</html>
"""


def render_section_page(section_key: str, section_title: str, tagline: str, bot_username: str = "") -> str:
    return (
        SECTION_HTML
        .replace("__SECTION_KEY__", section_key)
        .replace("__SECTION_TITLE__", section_title)
        .replace("__TAGLINE__", tagline)
        .replace("__BOT_USERNAME__", bot_username)
    )
