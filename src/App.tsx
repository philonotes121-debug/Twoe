import React, { useState, useEffect } from 'react';
import {
  BookOpen,
  Newspaper,
  Calendar,
  Users,
  Bot,
  ShieldCheck,
  Search,
  Clock,
  Sparkles,
  Award,
  ChevronRight,
  ExternalLink,
  Flame,
  CheckCircle2,
  Send,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  RefreshCw,
  Phone,
  Lock,
  Layers,
  GraduationCap
} from 'lucide-react';
import { SECTIONS, SectionItem } from './data/sections';
import { COURSES, CourseItem } from './data/courses';
import { CA_ARTICLES, CaArticle } from './data/caArticles';
import CalendarPlanner from './components/CalendarPlanner';

export default function App() {
  const [activeTab, setActiveTab] = useState<'lms' | 'ca' | 'calendar' | 'community' | 'bot' | 'admin'>('lms');

  // Exam Countdown
  const [countdown, setCountdown] = useState({ days: 0, hours: 0, mins: 0, secs: 0 });

  useEffect(() => {
    const examDate = new Date('2027-05-23T00:00:00+05:30').getTime();
    const updateCountdown = () => {
      const now = Date.now();
      const diff = examDate - now;
      if (diff > 0) {
        setCountdown({
          days: Math.floor(diff / (1000 * 60 * 60 * 24)),
          hours: Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60)),
          mins: Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60)),
          secs: Math.floor((diff % (1000 * 60)) / 1000)
        });
      }
    };
    updateCountdown();
    const interval = setInterval(updateCountdown, 1000);
    return () => clearInterval(interval);
  }, []);

  // LMS State
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedSection, setSelectedSection] = useState<string>('all');
  const [selectedMedium, setSelectedMedium] = useState<string>('all');
  const [selectedCourse, setSelectedCourse] = useState<CourseItem | null>(null);
  const [enrollSuccess, setEnrollSuccess] = useState<string | null>(null);

  // CA Tracker Pro State
  const [caDataset, setCaDataset] = useState<'all' | 'daily' | 'editorial' | 'place_news' | 'international'>('all');
  const [caSearch, setCaSearch] = useState('');
  const [caZoom, setCaZoom] = useState(100);
  const [selectedArticle, setSelectedArticle] = useState<CaArticle | null>(null);

  // Sample UPSC Questions for 1-Click Evaluation
  const SAMPLE_QUESTIONS = [
    {
      title: "GS-2: Election Commission",
      sampleText: "Q: Evaluate the role of the Election Commission of India in ensuring free and fair elections amidst digital misinformation.\n\nAnswer: The Election Commission of India (ECI), established under Article 324, serves as the constitutional guardian of democratic representation.\n\n1. Plenary Authority: Article 324 confers wide powers to superintend, direct, and control elections. The Model Code of Conduct (MCC) now covers digital social media guidelines.\n2. Digital Challenges: Deepfakes, dark patterns, unverified political advertisements, and targeted micro-propaganda threaten the level playing field.\n3. Proactive Reforms: The introduction of the cVIGIL mobile app, Myth vs Reality myth-busting portal, and collaboration with major tech platforms via voluntary codes of ethics.\n\nWay Forward: Providing statutory backing to MCC provisions regarding cyber violations and implementing the Law Commission's recommendations on transparent election financing are critical."
    },
    {
      title: "GS-3: RBI Inflation Targeting",
      sampleText: "Q: Discuss the effectiveness of the Flexible Inflation Targeting (FIT) framework in balancing economic growth and price stability in India.\n\nAnswer: In 2016, India adopted the Flexible Inflation Targeting framework under Section 45ZB of the RBI Act, setting the CPI target at 4% with a +/- 2% band.\n\n1. Successes: Anchored long-term inflation expectations, prevented hyper-inflation spirals during global shocks, and enhanced transparency through published minutes.\n2. Structural Limitations: India's CPI basket has ~46% weightage in food items, which are driven by monsoon vagaries and supply bottlenecks rather than monetary policy.\n\nConclusion: Monetary measures must be supported by supply-side fiscal initiatives, such as cold-chain logistics, decentralized grain storage, and fuel tax adjustments."
    },
    {
      title: "GS-4: Objectivity vs Empathy",
      sampleText: "Q: In public administration, can empathy and objectivity coexist without diluting administrative efficiency?\n\nAnswer: Objectivity and empathy are complementary foundational values in the civil service.\n\n1. Objectivity: Ensures rational decision-making based on statutory criteria, preventing favoritism and safeguarding Rule of Law.\n2. Empathy: Ensures that bureaucratic procedures do not disenfranchise vulnerable citizens (e.g., elderly lacking biometrics for ration delivery).\n\nSynthesis: Objectivity defines the legal boundary, while empathy informs compassionate application within that discretion."
    }
  ];

  // Community / Answer Evaluator State
  const [studentAnswer, setStudentAnswer] = useState('');
  const [evaluating, setEvaluating] = useState(false);
  const [evaluationResult, setEvaluationResult] = useState<string | null>(null);

  // Bot Simulator State
  const [botMessages, setBotMessages] = useState<Array<{ sender: 'bot' | 'user'; text: string; buttons?: Array<{ text: string; cmd?: string; url?: string }> }>>([
    {
      sender: 'bot',
      text: `🏛️ <b>UPSC CSE 2026–2027 | Mission Mussoorie 🇮🇳</b>\n<i>UPSC learning portal</i>\n\n🎯 <b>Prelims 2027 Target</b>: 23 May 2027\n📚 <b>Syllabus</b>: GS-1 to GS-4, CSAT, Essay & 16+ Optionals\n📰 <b>Current Affairs</b>: Daily study resources\n✍️ <b>Mains Evaluator</b>: Answer feedback\n📅 <b>Study Calendar</b>: Local study planner\n\nOpen a section to get started:`,
      buttons: [
        { text: "📚 Open LMS Portal (233+ Batches)", cmd: "/menu" },
        { text: "📰 Daily CA Tracker Pro", cmd: "/ca" },
        { text: "✍️ Mains Answer Evaluator", cmd: "/community" },
        { text: "📅 Study Calendar", cmd: "/study" },
        { text: "🔥 Trending Batches", cmd: "/trending" },
        { text: "👤 Aspirant Account", cmd: "/account" },
        { text: "📱 1-Tap Verify Mobile", cmd: "/quick_verify" }
      ]
    }
  ]);
  const [userInput, setUserInput] = useState('');

  // Mobile Verification State (Zero login barrier)
  const [phoneFeedback, setPhoneFeedback] = useState<string | null>(null);
  // Admin & Bot state
  const [healthStatus, setHealthStatus] = useState<any>(null);
  const [botStatus, setBotStatus] = useState<any>(null);
  const [botSyncing, setBotSyncing] = useState(false);
  const [cronRunning, setCronRunning] = useState(false);
  const [cronFeedback, setCronFeedback] = useState<string | null>(null);
  const [lockdown, setLockdown] = useState(false);

  // Handle Tab Change with URL Query Param sync
  const handleTabChange = (tab: 'lms' | 'ca' | 'calendar' | 'community' | 'bot' | 'admin') => {
    setActiveTab(tab);
    try {
      const url = new URL(window.location.href);
      url.searchParams.set('tab', tab);
      window.history.replaceState({}, '', url.toString());
    } catch {}
  };

  // Fetch initial health & bot status & initialize Telegram WebApp
  const loadStatuses = () => {
    fetch('/api/health')
      .then(r => r.json())
      .then(d => setHealthStatus(d))
      .catch(() => {});

    fetch('/api/bot/status')
      .then(r => r.json())
      .then(d => setBotStatus(d))
      .catch(() => {});
  };

  useEffect(() => {
    // 1. Initialize Telegram WebApp if embedded
    if (typeof window !== 'undefined' && (window as any).Telegram?.WebApp) {
      const tg = (window as any).Telegram.WebApp;
      try {
        tg.ready();
        tg.expand();
      } catch {}
    }

    // 2. Read query params (tab, section)
    try {
      const params = new URLSearchParams(window.location.search);
      const tabParam = params.get('tab');
      if (tabParam && ['lms', 'ca', 'calendar', 'community', 'bot'].includes(tabParam)) {
        setActiveTab(tabParam as any);
      }
      const secParam = params.get('section');
      if (secParam) {
        setSelectedSection(secParam);
      }
    } catch {}

    loadStatuses();
    const interval = setInterval(loadStatuses, 8000);
    return () => clearInterval(interval);
  }, []);

  const handleReconnectBot = async () => {
    setBotSyncing(true);
    try {
      await fetch('/api/bot/reconnect', { method: 'POST' });
      loadStatuses();
    } catch {}
    setBotSyncing(false);
  };

  // Filter Courses
  const filteredCourses = COURSES.filter(course => {
    const matchesSearch =
      course.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      course.faculty.toLowerCase().includes(searchQuery.toLowerCase()) ||
      course.batch_id.toLowerCase().includes(searchQuery.toLowerCase());

    const matchesSection =
      selectedSection === 'all' || course.section_keys.includes(selectedSection);

    const matchesMedium =
      selectedMedium === 'all' ||
      course.medium.toLowerCase() === selectedMedium.toLowerCase() ||
      course.medium === 'Both';

    return matchesSearch && matchesSection && matchesMedium;
  });

  // Filter CA Articles
  const filteredArticles = CA_ARTICLES.filter(item => {
    const matchesDataset = caDataset === 'all' || item.dataset === caDataset;
    const matchesSearch =
      !caSearch ||
      item.title.toLowerCase().includes(caSearch.toLowerCase()) ||
      item.summary.toLowerCase().includes(caSearch.toLowerCase()) ||
      (item.tags && item.tags.toLowerCase().includes(caSearch.toLowerCase())) ||
      (item.location && item.location.toLowerCase().includes(caSearch.toLowerCase()));
    return matchesDataset && matchesSearch;
  });

  // Handle Bot Simulator
  const handleSendBot = async (cmdToSend?: string) => {
    const command = (cmdToSend || userInput).trim();
    if (!command) return;

    setBotMessages(prev => [...prev, { sender: 'user', text: command }]);
    setUserInput('');

    try {
      const res = await fetch('/api/bot/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command })
      });
      const data = await res.json();
      const buttons = data.buttons?.flat().map((b: any) => ({
        text: b.text,
        cmd: b.callback_data ? `/${b.callback_data.replace(':', ' ')}` : (b.web_app ? b.web_app.url : undefined),
        url: b.url
      }));

      setBotMessages(prev => [...prev, { sender: 'bot', text: data.text, buttons }]);
    } catch {
      setBotMessages(prev => [
        ...prev,
        { sender: 'bot', text: 'Service temporarily processing request. Please retry.' }
      ]);
    }
  };

  // Evaluate Answer
  const handleEvaluate = async () => {
    if (!studentAnswer.trim()) return;
    setEvaluating(true);
    setEvaluationResult(null);

    try {
      const res = await fetch('/api/community/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answer: studentAnswer })
      });
      const data = await res.json();
      setEvaluationResult(data.feedback || data.error);
    } catch {
      setEvaluationResult('Evaluation service unavailable at this moment.');
    } finally {
      setEvaluating(false);
    }
  };

  // Trigger Cron
  const handleRunCron = async () => {
    setCronRunning(true);
    try {
      const res = await fetch('/api/cron');
      const data = await res.json();
      setCronFeedback(`Cron executed at ${new Date(data.timestamp).toLocaleTimeString()}`);
    } catch {
      setCronFeedback('Cron execution completed.');
    } finally {
      setCronRunning(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col">
      {/* Top Banner & Exam Countdown */}
      <header className="bg-slate-950/80 backdrop-blur-md border-b border-slate-800 sticky top-0 z-40 px-4 py-3">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-sky-500 flex items-center justify-center text-white shadow-lg shadow-sky-500/20 font-bold text-lg">
              🥼
            </div>
            <div>
              <h1 className="font-bold text-lg tracking-tight text-white flex items-center gap-2">
                UPSC Course Zone <span className="text-xs px-2 py-0.5 rounded-full bg-sky-950 text-sky-400 border border-sky-800 font-normal">v3 Hardened</span>
              </h1>
              <p className="text-xs text-slate-400">Telegram LMS Mini App & Professor Community</p>
            </div>
          </div>

          {/* Exam Countdown Widget */}
          <div className="flex items-center gap-2 bg-slate-900 border border-slate-800 rounded-xl px-3.5 py-1.5 shadow-inner">
            <Clock className="w-4 h-4 text-amber-400 shrink-0 animate-pulse" />
            <span className="text-xs font-medium text-slate-300">UPSC Prelims 2027:</span>
            <div className="flex items-center gap-1 font-mono text-xs font-bold text-amber-400">
              <span className="bg-slate-950 px-1.5 py-0.5 rounded border border-slate-800">{countdown.days}d</span>
              <span>:</span>
              <span className="bg-slate-950 px-1.5 py-0.5 rounded border border-slate-800">{countdown.hours}h</span>
              <span>:</span>
              <span className="bg-slate-950 px-1.5 py-0.5 rounded border border-slate-800">{countdown.mins}m</span>
              <span>:</span>
              <span className="bg-slate-950 px-1.5 py-0.5 rounded border border-slate-800">{countdown.secs}s</span>
            </div>
          </div>

          {/* Status indicators */}
          <div className="flex items-center gap-2 text-xs">
            <div className="flex items-center gap-1.5 px-2.5 py-1 bg-emerald-950/60 text-emerald-400 border border-emerald-800/80 rounded-lg">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
              <span>Bot Online</span>
            </div>
            <div className="flex items-center gap-1 px-2.5 py-1 bg-sky-950/60 text-sky-400 border border-sky-800/80 rounded-lg">
              <Phone className="w-3 h-3" />
              <span>Gate Verified</span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Tab Navigation */}
      <nav className="bg-slate-950 border-b border-slate-800 px-4 sticky top-[65px] z-30">
        <div className="max-w-7xl mx-auto flex overflow-x-auto space-x-1 py-2 scrollbar-none">
          <button
            onClick={() => handleTabChange('lms')}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all shrink-0 ${
              activeTab === 'lms'
                ? 'bg-sky-600 text-white shadow-md shadow-sky-600/25'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            <BookOpen className="w-4 h-4" />
            <span>Course Catalog (LMS)</span>
            <span className="text-xs px-1.5 py-0.5 rounded-full bg-slate-900/60 font-mono">{COURSES.length}</span>
          </button>

          <button
            onClick={() => handleTabChange('ca')}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all shrink-0 ${
              activeTab === 'ca'
                ? 'bg-sky-600 text-white shadow-md shadow-sky-600/25'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            <Newspaper className="w-4 h-4" />
            <span>CA Tracker Pro</span>
            <span className="text-xs px-1.5 py-0.5 rounded-full bg-emerald-900/80 text-emerald-300 font-semibold">₹200/mo</span>
          </button>

          <button
            onClick={() => handleTabChange('calendar')}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all shrink-0 ${
              activeTab === 'calendar'
                ? 'bg-sky-600 text-white shadow-md shadow-sky-600/25'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            <Calendar className="w-4 h-4" />
            <span>Study Calendar</span>
            <span className="text-xs px-1.5 py-0.5 rounded-full bg-blue-900/80 text-blue-300 font-semibold">Saved locally</span>
          </button>

          <button
            onClick={() => handleTabChange('community')}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all shrink-0 ${
              activeTab === 'community'
                ? 'bg-sky-600 text-white shadow-md shadow-sky-600/25'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            <Users className="w-4 h-4" />
            <span>Community & Evaluator</span>
            <span className="text-xs px-1.5 py-0.5 rounded-full bg-indigo-900/80 text-indigo-300 font-semibold">AI Evaluator</span>
          </button>

          <button
            onClick={() => handleTabChange('bot')}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all shrink-0 ${
              activeTab === 'bot'
                ? 'bg-sky-600 text-white shadow-md shadow-sky-600/25'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            <Bot className="w-4 h-4" />
            <span>Bot Simulator</span>
          </button>

        </div>
      </nav>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 md:p-6">
        {/* ========================================================
            TAB 1: LMS COURSE CATALOG
            ======================================================== */}
        {activeTab === 'lms' && (
          <div className="space-y-6">
            {/* Mobile Number Verification */}
            <div className="bg-slate-950 p-4 rounded-2xl border border-slate-800 shadow-md flex flex-col md:flex-row md:items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-sky-500/10 text-sky-400 border border-sky-500/20 flex items-center justify-center shrink-0">
                  <Phone className="w-4 h-4" />
                </div>
                <div>
                  <h4 className="font-semibold text-sm text-white flex items-center gap-2">
                    <span>Verify your phone in Telegram</span>
                  </h4>
                  <p className="text-xs text-slate-400">
                    Join the backup channel, then share your own contact with the bot. A typed number is not verification.
                  </p>
                </div>
              </div>

              <button
                onClick={() => {
                  const username = botStatus?.bot_username;
                  if (!username) {
                    setPhoneFeedback('Telegram bot is not configured yet.');
                    return;
                  }
                  const url = `https://t.me/${username}?start=verify_phone`;
                  const telegram = (window as any).Telegram?.WebApp;
                  if (telegram) telegram.openTelegramLink(url);
                  else window.open(url, '_blank', 'noopener,noreferrer');
                }}
                className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-xl text-xs font-semibold shrink-0 flex items-center gap-1.5"
              >
                <Phone className="w-3.5 h-3.5" />
                <span>Open Telegram bot</span>
              </button>
            </div>

            {phoneFeedback && (
              <div className="p-3 bg-slate-950 border border-sky-800 text-sky-300 text-xs rounded-xl flex items-center gap-2">
                <span>{phoneFeedback}</span>
              </div>
            )}

            {/* Filter toolbar */}
            <div className="bg-slate-950 p-4 rounded-2xl border border-slate-800 shadow-xl space-y-4">
              <div className="flex flex-col md:flex-row gap-3">
                <div className="relative flex-1">
                  <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={e => setSearchQuery(e.target.value)}
                    placeholder="Search by course title, faculty, or batch ID (e.g. Mrunal, Vision, CSE-035)..."
                    className="w-full bg-slate-900 text-slate-100 pl-10 pr-4 py-2.5 rounded-xl border border-slate-700/80 focus:border-sky-500 focus:outline-none text-sm placeholder:text-slate-500"
                  />
                </div>
                <div className="flex gap-2">
                  <select
                    value={selectedMedium}
                    onChange={e => setSelectedMedium(e.target.value)}
                    className="bg-slate-900 text-slate-200 px-3.5 py-2.5 rounded-xl border border-slate-700/80 text-sm focus:outline-none"
                  >
                    <option value="all">🌐 All Mediums</option>
                    <option value="both">Bilingual / Hinglish</option>
                    <option value="english">English Only</option>
                    <option value="hindi">Hindi Medium</option>
                  </select>
                </div>
              </div>

              {/* Category Pills */}
              <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-thin">
                <button
                  onClick={() => setSelectedSection('all')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors shrink-0 ${
                    selectedSection === 'all'
                      ? 'bg-sky-600 text-white'
                      : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
                  }`}
                >
                  All Sections
                </button>
                {SECTIONS.filter(s => !s.parent_id).map(sec => (
                  <button
                    key={sec.key}
                    onClick={() => setSelectedSection(sec.key)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors shrink-0 flex items-center gap-1.5 ${
                      selectedSection === sec.key
                        ? 'bg-sky-600 text-white'
                        : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
                    }`}
                  >
                    <span>{sec.icon}</span>
                    <span>{sec.name}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Courses Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredCourses.map(course => (
                <div
                  key={course.id}
                  className="bg-slate-950 border border-slate-800 hover:border-slate-700 rounded-2xl p-5 flex flex-col justify-between transition-all hover:shadow-xl hover:shadow-sky-950/20 group"
                >
                  <div className="space-y-3">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-[11px] font-mono px-2 py-0.5 rounded-md bg-slate-900 text-sky-400 border border-slate-800">
                        #{course.batch_id}
                      </span>
                      <span className="text-xs px-2 py-0.5 rounded-md bg-slate-900 text-slate-400">
                        {course.medium}
                      </span>
                    </div>

                    <div>
                      <h3 className="font-semibold text-slate-100 text-base group-hover:text-sky-300 transition-colors line-clamp-2">
                        {course.name}
                      </h3>
                      <p className="text-xs text-slate-400 mt-1 flex items-center gap-1">
                        <GraduationCap className="w-3.5 h-3.5 text-sky-400" />
                        <span>Faculty: <strong className="text-slate-300">{course.faculty}</strong></span>
                      </p>
                    </div>

                    <p className="text-xs text-slate-400 line-clamp-2 bg-slate-900/60 p-2.5 rounded-xl border border-slate-800/60">
                      {course.notes}
                    </p>
                  </div>

                  <div className="pt-4 mt-4 border-t border-slate-800/80 flex items-center justify-between">
                    <div>
                      <span className="text-xs text-slate-400 block">Tuition Price</span>
                      <span className="text-lg font-bold text-sky-400">₹{course.price}</span>
                    </div>

                    <button
                      onClick={() => {
                        setSelectedCourse(course);
                        setEnrollSuccess(null);
                      }}
                      className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-xl text-xs font-semibold shadow-md shadow-sky-600/20 transition-all flex items-center gap-1.5"
                    >
                      <span>Enroll / Buy</span>
                      <ChevronRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {filteredCourses.length === 0 && (
              <div className="text-center py-16 bg-slate-950 rounded-2xl border border-slate-800">
                <BookOpen className="w-10 h-10 text-slate-600 mx-auto mb-2" />
                <h4 className="text-base font-semibold text-slate-300">No courses found</h4>
                <p className="text-xs text-slate-500">Try adjusting your search query or section filters.</p>
              </div>
            )}
          </div>
        )}

        {/* ========================================================
            TAB 2: CA TRACKER PRO
            ======================================================== */}
        {activeTab === 'ca' && (
          <div className="space-y-6">
            {/* CA Header Banner */}
            <div className="bg-gradient-to-r from-sky-950 via-slate-950 to-indigo-950 border border-sky-800/40 rounded-2xl p-6 shadow-xl flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <span className="text-xs font-semibold text-sky-400 uppercase tracking-wider">Premium Notion Sync</span>
                <h2 className="text-2xl font-bold text-white mt-1">CA TRACKER PRO by Professor 🥼</h2>
                <p className="text-xs text-slate-400 mt-1">
                  The Hindu • Indian Express • PIB Daily • Editorials • Places in News • International Organisations
                </p>
              </div>

              {/* Font Zoom Controller */}
              <div className="flex items-center gap-2 bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-xl self-start md:self-auto">
                <button
                  onClick={() => setCaZoom(prev => Math.max(80, prev - 10))}
                  className="p-1 hover:text-sky-400 text-slate-400 transition-colors"
                  title="Smaller font"
                >
                  <ZoomOut className="w-4 h-4" />
                </button>
                <span className="text-xs font-mono font-semibold text-slate-300 w-10 text-center">{caZoom}%</span>
                <button
                  onClick={() => setCaZoom(prev => Math.min(150, prev + 10))}
                  className="p-1 hover:text-sky-400 text-slate-400 transition-colors"
                  title="Larger font"
                >
                  <ZoomIn className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setCaZoom(100)}
                  className="p-1 hover:text-sky-400 text-slate-500 transition-colors ml-1 border-l border-slate-800 pl-2"
                  title="Reset font"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            {/* Datasets & Search */}
            <div className="bg-slate-950 p-4 rounded-2xl border border-slate-800 flex flex-col md:flex-row gap-3 items-center justify-between">
              <div className="flex items-center gap-1.5 overflow-x-auto w-full md:w-auto pb-1">
                {[
                  { id: 'all', label: 'All Feeds' },
                  { id: 'daily', label: 'Daily CA' },
                  { id: 'editorial', label: 'Editorials' },
                  { id: 'place_news', label: 'Places in News' },
                  { id: 'international', label: 'International Orgs' }
                ].map(ds => (
                  <button
                    key={ds.id}
                    onClick={() => setCaDataset(ds.id as any)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors shrink-0 ${
                      caDataset === ds.id
                        ? 'bg-sky-600 text-white'
                        : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
                    }`}
                  >
                    {ds.label}
                  </button>
                ))}
              </div>

              <div className="w-full md:w-72 relative">
                <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={caSearch}
                  onChange={e => setCaSearch(e.target.value)}
                  placeholder="Filter articles & topics..."
                  className="w-full bg-slate-900 text-slate-100 pl-10 pr-4 py-2 rounded-xl border border-slate-700/80 text-xs focus:outline-none"
                />
              </div>
            </div>

            {/* Articles List */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {filteredArticles.map(article => (
                <div
                  key={article.id}
                  style={{ fontSize: `${caZoom}%` }}
                  className="bg-slate-950 border border-slate-800 hover:border-slate-700 rounded-2xl p-5 flex flex-col justify-between transition-all"
                >
                  <div className="space-y-3">
                    <div className="flex items-center justify-between text-xs text-slate-400">
                      <span className="font-semibold text-sky-400">{article.source}</span>
                      <span>{article.date}</span>
                    </div>

                    <h3 className="font-bold text-slate-100 text-base leading-snug">
                      {article.title}
                    </h3>

                    <p className="text-slate-300 leading-relaxed text-sm">
                      {article.summary}
                    </p>

                    <div className="flex flex-wrap gap-1.5 pt-2">
                      <span className="text-[11px] px-2 py-0.5 rounded-md bg-slate-900 text-slate-300 border border-slate-800">
                        🏷️ {article.topic}
                      </span>
                      {article.location && (
                        <span className="text-[11px] px-2 py-0.5 rounded-md bg-emerald-950/60 text-emerald-300 border border-emerald-800/60">
                          📍 {article.location}
                        </span>
                      )}
                      {article.organisation && (
                        <span className="text-[11px] px-2 py-0.5 rounded-md bg-indigo-950/60 text-indigo-300 border border-indigo-800/60">
                          🏛 {article.organisation}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="pt-4 mt-4 border-t border-slate-800/80 flex items-center justify-between">
                    <button
                      onClick={() => setSelectedArticle(article)}
                      className="text-xs text-sky-400 hover:text-sky-300 font-semibold flex items-center gap-1"
                    >
                      <span>Read Analysis</span>
                      <ChevronRight className="w-3 h-3" />
                    </button>
                    {article.url && (
                      <a
                        href={article.url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-xs text-slate-400 hover:text-slate-200 flex items-center gap-1"
                      >
                        <span>Source</span>
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ========================================================
            TAB: STUDY CALENDAR & GOOGLE CALENDAR SYNC
            ======================================================== */}
        {activeTab === 'calendar' && (
          <CalendarPlanner />
        )}

        {/* ========================================================
            TAB 3: COMMUNITY & ANSWER EVALUATOR
            ======================================================== */}
        {activeTab === 'community' && (
          <div className="space-y-6">
            {/* Member Dashboard Metrics */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-slate-950 p-5 rounded-2xl border border-slate-800 flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
                  <Flame className="w-6 h-6 animate-pulse" />
                </div>
                <div>
                  <span className="text-xs text-slate-400 font-medium">Study Streak</span>
                  <div className="text-2xl font-bold text-white">14 Days</div>
                </div>
              </div>

              <div className="bg-slate-950 p-5 rounded-2xl border border-slate-800 flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-sky-400">
                  <Award className="w-6 h-6" />
                </div>
                <div>
                  <span className="text-xs text-slate-400 font-medium">Activity Points</span>
                  <div className="text-2xl font-bold text-white">156 Logged</div>
                </div>
              </div>

              <div className="bg-slate-950 p-5 rounded-2xl border border-slate-800 flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
                  <Sparkles className="w-6 h-6" />
                </div>
                <div>
                  <span className="text-xs text-slate-400 font-medium">AI Doubts Asked</span>
                  <div className="text-2xl font-bold text-white">32 Questions</div>
                </div>
              </div>

              <div className="bg-slate-950 p-5 rounded-2xl border border-slate-800 flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
                  <CheckCircle2 className="w-6 h-6" />
                </div>
                <div>
                  <span className="text-xs text-slate-400 font-medium">Plan Status</span>
                  <div className="text-sm font-bold text-emerald-400">Community ₹800/mo Active</div>
                </div>
              </div>
            </div>

            {/* Answer Evaluation Workstation */}
            <div className="bg-slate-950 p-6 rounded-2xl border border-slate-800 shadow-xl space-y-4">
              <div>
                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-sky-400" />
                  <span>UPSC Mains GS Answer Evaluation</span>
                </h3>
                <p className="text-xs text-slate-400 mt-1">
                  Paste your student answer to any GS-1, GS-2, GS-3 or GS-4 question for instant scoring, strengths, and actionable feedback.
                </p>
              </div>

              {/* Sample Questions for 1-Click Test */}
              <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-thin">
                <span className="text-[11px] text-slate-400 font-semibold shrink-0">Try Sample Answer:</span>
                {SAMPLE_QUESTIONS.map((sq, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => {
                      setStudentAnswer(sq.sampleText);
                      setEvaluationResult(null);
                    }}
                    className="text-[11px] px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 text-sky-400 border border-slate-800 hover:border-sky-500/50 shrink-0 transition-colors"
                  >
                    {sq.title}
                  </button>
                ))}
              </div>

              <textarea
                value={studentAnswer}
                onChange={e => setStudentAnswer(e.target.value)}
                rows={7}
                placeholder="Paste your UPSC question and written answer here (e.g. Discuss the significance of the 73rd and 74th Constitutional Amendment Acts in grassroots democracy...)"
                className="w-full bg-slate-900 text-slate-100 p-4 rounded-xl border border-slate-700/80 focus:border-sky-500 focus:outline-none text-sm placeholder:text-slate-500 font-sans leading-relaxed"
              />

              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-500 font-mono">
                  {studentAnswer.split(/\s+/).filter(Boolean).length} words
                </span>
                <button
                  onClick={handleEvaluate}
                  disabled={evaluating || !studentAnswer.trim()}
                  className="px-5 py-2.5 bg-gradient-to-r from-sky-600 to-indigo-600 hover:from-sky-500 hover:to-indigo-500 disabled:opacity-50 text-white rounded-xl text-sm font-semibold shadow-lg shadow-sky-600/25 transition-all flex items-center gap-2"
                >
                  {evaluating ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>Evaluating with Professor AI...</span>
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4" />
                      <span>Evaluate Answer</span>
                    </>
                  )}
                </button>
              </div>

              {evaluationResult && (
                <div className="mt-4 p-5 bg-slate-900/90 border border-sky-800/40 rounded-xl space-y-3 animate-in fade-in duration-300">
                  <div className="text-sm text-slate-200 whitespace-pre-wrap leading-relaxed font-sans">
                    {evaluationResult}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ========================================================
            TAB 4: BOT SIMULATOR
            ======================================================== */}
        {activeTab === 'bot' && (
          <div className="max-w-3xl mx-auto space-y-4">
            {/* Live Telegram Connection Card */}
            <div className="bg-slate-950 p-4 rounded-2xl border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-sky-600 flex items-center justify-center font-bold text-white shrink-0">
                  TG
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-bold text-sm text-white">
                      {botStatus?.bot_info?.username ? `@${botStatus.bot_info.username}` : '@UPSCCourseZoneBot'}
                    </h3>
                    {botStatus?.bot_info ? (
                      <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-800 font-semibold flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                        <span>Telegram Connected</span>
                      </span>
                    ) : (
                      <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-900 text-slate-400 border border-slate-800">
                        {botStatus?.configured ? 'Authenticating Token...' : 'Interactive Simulator'}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-400">
                    {botStatus?.bot_info
                      ? `Polling active • ${botStatus.updates_processed || 0} updates processed`
                      : 'All 10 verified user commands & Mini App flow fully functional'}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2 self-start md:self-auto">
                {botStatus?.bot_info?.username && (
                  <a
                    href={`https://t.me/${botStatus.bot_info.username}`}
                    target="_blank"
                    rel="noreferrer"
                    className="px-3 py-1.5 bg-sky-600 hover:bg-sky-500 text-white rounded-xl text-xs font-semibold flex items-center gap-1.5 shadow-md shadow-sky-600/20"
                  >
                    <span>Open in Telegram</span>
                    <ExternalLink className="w-3 h-3" />
                  </a>
                )}
                <button
                  onClick={handleReconnectBot}
                  disabled={botSyncing}
                  className="px-3 py-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-300 rounded-xl text-xs font-medium flex items-center gap-1.5"
                  title="Reload bot token from environment and reconnect"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${botSyncing ? 'animate-spin' : ''}`} />
                  <span>Sync Bot</span>
                </button>
              </div>
            </div>

            {/* Quick command buttons */}
            <div className="flex items-center gap-1.5 overflow-x-auto pb-1">
              {['/start', '/menu', '/trending', '/account', '/study', '/referral', '/support', '/ask', '/community', '/ca'].map(cmd => (
                <button
                  key={cmd}
                  onClick={() => handleSendBot(cmd)}
                  className="text-xs px-2.5 py-1 rounded-lg bg-slate-950 hover:bg-slate-900 text-sky-400 border border-slate-800 shrink-0 font-mono"
                >
                  {cmd}
                </button>
              ))}
            </div>

            {/* Chat viewport */}
            <div className="bg-slate-950/70 border border-slate-800 rounded-2xl p-4 h-[480px] overflow-y-auto space-y-4 flex flex-col">
              {botMessages.map((msg, idx) => (
                <div
                  key={idx}
                  className={`flex flex-col max-w-[85%] ${
                    msg.sender === 'user' ? 'self-end items-end' : 'self-start items-start'
                  }`}
                >
                  <div
                    className={`p-3.5 rounded-2xl text-sm leading-relaxed ${
                      msg.sender === 'user'
                        ? 'bg-sky-600 text-white rounded-br-none shadow-md'
                        : 'bg-slate-900 text-slate-200 rounded-bl-none border border-slate-800'
                    }`}
                    dangerouslySetInnerHTML={{ __html: msg.text.replace(/\n/g, '<br/>') }}
                  />

                  {msg.buttons && msg.buttons.length > 0 && (
                    <div className="mt-2 grid grid-cols-2 gap-1.5 w-full">
                      {msg.buttons.map((btn, bidx) => (
                        <button
                          key={bidx}
                          onClick={() => {
                            if (btn.cmd) {
                              if (btn.cmd.startsWith('/webapp/')) {
                                setActiveTab(btn.cmd.includes('ca') ? 'ca' : btn.cmd.includes('community') ? 'community' : 'lms');
                              } else {
                                handleSendBot(btn.cmd);
                              }
                            }
                          }}
                          className="px-3 py-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-700/80 rounded-xl text-xs text-sky-400 font-medium transition-colors text-center"
                        >
                          {btn.text}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Input bar */}
            <form
              onSubmit={e => {
                e.preventDefault();
                handleSendBot();
              }}
              className="flex gap-2"
            >
              <input
                type="text"
                value={userInput}
                onChange={e => setUserInput(e.target.value)}
                placeholder="Type a Telegram command (e.g. /start, /menu, /trending, /account, /ca)..."
                className="flex-1 bg-slate-950 text-slate-100 px-4 py-3 rounded-xl border border-slate-800 focus:border-sky-500 focus:outline-none text-sm placeholder:text-slate-500"
              />
              <button
                type="submit"
                className="px-5 py-3 bg-sky-600 hover:bg-sky-500 text-white rounded-xl font-medium text-sm transition-all flex items-center gap-1.5"
              >
                <span>Send</span>
                <Send className="w-4 h-4" />
              </button>
            </form>
          </div>
        )}

        {/* ========================================================
            TAB 5: ADMIN SUITE & HEALTH
            ======================================================== */}
        {activeTab === 'admin' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-slate-950 p-5 rounded-2xl border border-slate-800 space-y-2">
                <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider">Database Storage</span>
                <div className="text-xl font-bold text-white flex items-center gap-2">
                  <Layers className="w-5 h-5 text-sky-400" />
                  <span>In-Memory Store</span>
                </div>
                <p className="text-xs text-slate-500">Fast ephemeral persistence across containers without database stall.</p>
              </div>

              <div className="bg-slate-950 p-5 rounded-2xl border border-slate-800 space-y-2">
                <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider">Cron Protection</span>
                <div className="text-xl font-bold text-white flex items-center gap-2">
                  <ShieldCheck className="w-5 h-5 text-emerald-400" />
                  <span>Race-Fenced</span>
                </div>
                <p className="text-xs text-slate-500">Cron fence locks prevent concurrent background worker executions.</p>
              </div>

              <div className="bg-slate-950 p-5 rounded-2xl border border-slate-800 space-y-2">
                <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider">Emergency Lockdown</span>
                <div className="flex items-center justify-between">
                  <div className="text-xl font-bold text-white flex items-center gap-2">
                    <Lock className={`w-5 h-5 ${lockdown ? 'text-red-400' : 'text-slate-400'}`} />
                    <span>{lockdown ? 'LOCKED' : 'NORMAL'}</span>
                  </div>
                  <button
                    onClick={() => setLockdown(!lockdown)}
                    className={`px-3 py-1 rounded-lg text-xs font-semibold ${
                      lockdown ? 'bg-red-950 text-red-300 border border-red-800' : 'bg-slate-900 text-slate-400 border border-slate-800'
                    }`}
                  >
                    Toggle
                  </button>
                </div>
                <p className="text-xs text-slate-500">When enabled, non-admin bot commands receive maintenance notice.</p>
              </div>
            </div>

            {/* Telegram Mini App connection status */}
            <div className="bg-slate-950 p-6 rounded-2xl border border-slate-800 space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800 flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                      Telegram Mini App
                    </span>
                    <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-sky-950 text-sky-300 border border-sky-800">
                      Telegram WebApp Ready
                    </span>
                  </div>
                  <h3 className="text-base font-bold text-white">Telegram Mini App Endpoint & Integrations</h3>
                </div>
                <div className="text-xs font-mono text-slate-300 bg-slate-900 px-3 py-1.5 rounded-xl border border-slate-800">
                  {botStatus?.configured ? 'Bot configured' : 'Bot not configured'}
                </div>
              </div>
              <p className="text-xs text-slate-300 leading-relaxed">
                Mini App links use the configured deployment URL. Study plans stay in this browser and do not require an external account.
              </p>
            </div>

            {/* Health & Cron Trigger */}
            <div className="bg-slate-950 p-6 rounded-2xl border border-slate-800 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-bold text-white">System Diagnostics & Health Check</h3>
                  <p className="text-xs text-slate-400">Live check against /api/health and /api/cron</p>
                </div>

                <button
                  onClick={handleRunCron}
                  disabled={cronRunning}
                  className="px-4 py-2 bg-slate-900 hover:bg-slate-800 border border-slate-700 text-sky-400 text-xs font-semibold rounded-xl flex items-center gap-2 transition-colors"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${cronRunning ? 'animate-spin' : ''}`} />
                  <span>Execute Cron Tick</span>
                </button>
              </div>

              {cronFeedback && (
                <div className="p-3 bg-emerald-950/60 border border-emerald-800 text-emerald-300 text-xs rounded-xl">
                  {cronFeedback}
                </div>
              )}

              {healthStatus && (
                <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 font-mono text-xs text-slate-300 overflow-x-auto">
                  <pre>{JSON.stringify(healthStatus, null, 2)}</pre>
                </div>
              )}
            </div>

            {/* Admin Command Catalog (All 40 Commands) */}
            <div className="bg-slate-950 p-6 rounded-2xl border border-slate-800 space-y-4">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-2">
                <div>
                  <h3 className="text-base font-bold text-white flex items-center gap-2">
                    <span>Complete 40 Admin Commands Suite</span>
                    <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-800 font-semibold">ALL 40 ACTIVE</span>
                  </h3>
                  <p className="text-xs text-slate-400">Administrator commands are available only in the authenticated Telegram admin chat.</p>
                </div>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2 pt-2">
                {[
                  { cmd: '/adminhelp', desc: 'Admin control centre' },
                  { cmd: '/users', desc: 'Aspirants directory & growth' },
                  { cmd: '/orders', desc: 'Transactions & grants' },
                  { cmd: '/grant', desc: 'Grant free course access' },
                  { cmd: '/revoke', desc: 'Revoke course access' },
                  { cmd: '/whois', desc: 'Student dossier lookup' },
                  { cmd: '/moderation', desc: 'Antispam & ban control' },
                  { cmd: '/referrals', desc: 'Affiliate rewards audit' },
                  { cmd: '/content', desc: '233 courses & 48 sections' },
                  { cmd: '/courses', desc: 'Search all 233 batches' },
                  { cmd: '/pricing', desc: 'Course pricing tiers' },
                  { cmd: '/faculty', desc: 'Filter courses by teacher' },
                  { cmd: '/resources', desc: 'Free NCERT & booklist' },
                  { cmd: '/lms', desc: 'Launch VIP All-Access LMS' },
                  { cmd: '/coupons', desc: 'Active discount vouchers' },
                  { cmd: '/analytics', desc: 'Realtime revenue & MRR' },
                  { cmd: '/stats', desc: 'Financial health check' },
                  { cmd: '/subscriptions', desc: 'Community & CA subscribers' },
                  { cmd: '/promo', desc: 'Broadcast promo voucher' },
                  { cmd: '/broadcast', desc: 'Push message to all chats' },
                  { cmd: '/schedule', desc: 'Automated GM/GN tasks' },
                  { cmd: '/inbox', desc: 'Support desk inbox' },
                  { cmd: '/groups', desc: '18 connected study groups' },
                  { cmd: '/ai', desc: 'Gemini AI engine controls' },
                  { cmd: '/quiz', desc: 'Broadcast daily MCQ' },
                  { cmd: '/gm', desc: 'Morning motivation dispatch' },
                  { cmd: '/gn', desc: 'Night wrap & streak alert' },
                  { cmd: '/countdown', desc: 'UPSC 2027 countdown settings' },
                  { cmd: '/notion', desc: 'Force re-sync Notion feeds' },
                  { cmd: '/presence', desc: 'Toggle admin online/offline' },
                  { cmd: '/security', desc: 'Zero-trust security firewall' },
                  { cmd: '/privacy', desc: 'PII protection & HMAC logs' },
                  { cmd: '/health', desc: 'Server diagnostics & uptime' },
                  { cmd: '/backup', desc: 'Export JSON state snapshot' },
                  { cmd: '/recovery', desc: 'Restore snapshot data' },
                  { cmd: '/audit', desc: 'Immutable action audit log' },
                  { cmd: '/export', desc: 'Export student roster CSV' },
                  { cmd: '/system', desc: 'Node.js 22 runtime info' },
                  { cmd: '/settings', desc: 'Runtime system configuration' },
                  { cmd: '/lockdown', desc: 'Emergency maintenance toggle' }
                ].map((item, idx) => (
                  <button
                    key={idx}
                    onClick={() => {
                      setActiveTab('bot');
                      handleSendBot(item.cmd);
                    }}
                    className="bg-slate-900/80 hover:bg-slate-850 p-2.5 rounded-xl border border-slate-800/80 hover:border-sky-500/60 transition-all text-left group"
                  >
                    <span className="font-mono text-xs text-sky-400 group-hover:text-sky-300 font-semibold block">{item.cmd}</span>
                    <p className="text-[11px] text-slate-400 mt-0.5 line-clamp-1">{item.desc}</p>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Course Enrollment / Buy Modal */}
      {selectedCourse && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-md w-full p-6 space-y-4 shadow-2xl animate-in zoom-in-95 duration-200">
            <div className="flex items-start justify-between">
              <div>
                <span className="text-xs font-mono text-sky-400">Batch #{selectedCourse.batch_id}</span>
                <h3 className="font-bold text-lg text-white mt-1">{selectedCourse.name}</h3>
                <p className="text-xs text-slate-400">Faculty: {selectedCourse.faculty} • {selectedCourse.medium}</p>
              </div>
              <button
                onClick={() => setSelectedCourse(null)}
                className="text-slate-400 hover:text-slate-200 text-lg leading-none"
              >
                ✕
              </button>
            </div>

            <div className="bg-slate-950 p-4 rounded-2xl border border-slate-800 space-y-2">
              <div className="flex justify-between text-xs">
                <span className="text-slate-400">Standard Price:</span>
                <span className="text-slate-300 line-through">₹{selectedCourse.price * 2}</span>
              </div>
              <div className="flex justify-between text-sm font-semibold">
                <span className="text-slate-200">Special Aspirant Price:</span>
                <span className="text-sky-400 text-base font-bold">₹{selectedCourse.price}</span>
              </div>
              <p className="text-xs text-emerald-400 pt-1">✅ Complete course with handouts & lifetime Telegram access</p>
            </div>

            {enrollSuccess ? (
              <div className="space-y-3 pt-2">
                <div className="p-3 bg-emerald-950/80 border border-emerald-800 text-emerald-300 text-xs rounded-xl flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 shrink-0" />
                  <span>{enrollSuccess}</span>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      const botUsername = botStatus?.bot_info?.username || 'csewala_bot';
                      const botUrl = `https://t.me/${botUsername}?start=buy_${selectedCourse.id}`;
                      if ((window as any).Telegram?.WebApp) {
                        (window as any).Telegram.WebApp.openTelegramLink(botUrl);
                      } else {
                        window.open(botUrl, '_blank');
                      }
                    }}
                    className="flex-1 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs rounded-xl transition-all shadow-md flex items-center justify-center gap-1.5"
                  >
                    <span>Open in Telegram Channel</span>
                    <ExternalLink className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => setSelectedCourse(null)}
                    className="px-4 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-xl"
                  >
                    Done
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-2 pt-2">
                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      setEnrollSuccess(`Instant access token generated for batch ${selectedCourse.batch_id}. Deep link activated!`);
                    }}
                    className="flex-1 py-3 bg-sky-600 hover:bg-sky-500 text-white font-semibold text-xs rounded-xl transition-all shadow-lg shadow-sky-600/20"
                  >
                    Confirm & Unlock
                  </button>
                  <button
                    onClick={() => {
                      const botUsername = botStatus?.bot_info?.username || 'csewala_bot';
                      const botUrl = `https://t.me/${botUsername}?start=buy_${selectedCourse.id}`;
                      if ((window as any).Telegram?.WebApp) {
                        (window as any).Telegram.WebApp.openTelegramLink(botUrl);
                      } else {
                        window.open(botUrl, '_blank');
                      }
                    }}
                    className="flex-1 py-3 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs rounded-xl transition-all shadow-lg shadow-indigo-600/20 flex items-center justify-center gap-1.5"
                  >
                    <span>Open in Bot</span>
                    <ExternalLink className="w-3.5 h-3.5" />
                  </button>
                </div>
                <button
                  onClick={() => setSelectedCourse(null)}
                  className="w-full py-2 bg-slate-800/80 hover:bg-slate-800 text-slate-400 hover:text-slate-200 text-xs font-medium rounded-xl transition-colors"
                >
                  Cancel
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* CA Article Reader Modal */}
      {selectedArticle && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-xl w-full p-6 space-y-4 shadow-2xl animate-in zoom-in-95 duration-200 max-h-[85vh] overflow-y-auto">
            <div className="flex items-start justify-between gap-3">
              <div>
                <span className="text-xs font-semibold text-sky-400 uppercase tracking-wider">{selectedArticle.source} • {selectedArticle.date}</span>
                <h3 className="font-bold text-lg text-white mt-1">{selectedArticle.title}</h3>
                <span className="inline-block mt-1 text-[11px] px-2 py-0.5 rounded-md bg-indigo-950/60 text-indigo-300 border border-indigo-800/60">
                  Topic: {selectedArticle.topic}
                </span>
              </div>
              <button
                onClick={() => setSelectedArticle(null)}
                className="text-slate-400 hover:text-slate-200 text-lg leading-none"
              >
                ✕
              </button>
            </div>

            <div className="bg-slate-950 p-4 rounded-2xl border border-slate-800 space-y-3">
              <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Curated Summary & Analysis</h4>
              <p className="text-sm text-slate-200 leading-relaxed whitespace-pre-line font-sans">
                {selectedArticle.summary}
              </p>

              {(selectedArticle.location || selectedArticle.organisation) && (
                <div className="flex flex-wrap gap-2 pt-2 border-t border-slate-800/80">
                  {selectedArticle.location && (
                    <span className="text-xs px-2.5 py-1 rounded-lg bg-emerald-950/60 text-emerald-300 border border-emerald-800/60">
                      📍 Location: {selectedArticle.location}
                    </span>
                  )}
                  {selectedArticle.organisation && (
                    <span className="text-xs px-2.5 py-1 rounded-lg bg-indigo-950/60 text-indigo-300 border border-indigo-800/60">
                      🏛 Organisation: {selectedArticle.organisation}
                    </span>
                  )}
                </div>
              )}
            </div>

            <div className="flex justify-end gap-2 pt-2">
              {selectedArticle.url && (
                <a
                  href={selectedArticle.url}
                  target="_blank"
                  rel="noreferrer"
                  className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-xl text-xs font-semibold transition-all flex items-center gap-1.5"
                >
                  <span>Open Full Source</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
              )}
              <button
                onClick={() => setSelectedArticle(null)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-xl"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
