import React, { useState, useEffect } from 'react';
import {
  Calendar as CalendarIcon,
  Clock,
  Plus,
  Trash2,
  CheckCircle,
  ExternalLink,
  RefreshCw,
  Sparkles,
  BookOpen,
  CalendarCheck,
  AlertCircle,
  LogOut,
  ChevronRight
} from 'lucide-react';
import {
  auth,
  initAuth,
  signInWithGoogleCalendar,
  getCalendarAccessToken,
  logOutGoogle,
  fetchGoogleCalendarEvents,
  createGoogleCalendarEvent,
  deleteGoogleCalendarEvent,
  GoogleCalendarItem,
  CalendarEventPayload
} from '../firebase';
import { User } from 'firebase/auth';

export interface StudyPlanItem {
  id: string;
  title: string;
  subject: string;
  date: string;
  startTime: string;
  endTime: string;
  description: string;
  isSyncedToGoogle: boolean;
  googleEventId?: string;
  completed: boolean;
}

const DEFAULT_UPSC_PLANS: StudyPlanItem[] = [
  {
    id: 'plan-1',
    title: '🌅 Morning GS-2 Polity: Laxmikanth Fundamental Rights & DPSP',
    subject: 'GS-2 Polity',
    date: '2026-10-03',
    startTime: '07:00',
    endTime: '09:30',
    description: 'Revise Articles 14 to 32, landmark judgments (Kesavananda Bharati, Minerva Mills) and MCQ practice.',
    isSyncedToGoogle: false,
    completed: false
  },
  {
    id: 'plan-2',
    title: '📰 CA Tracker Pro: The Hindu, Indian Express & PIB Analysis',
    subject: 'Current Affairs',
    date: '2026-10-03',
    startTime: '10:00',
    endTime: '11:30',
    description: 'Curated editorial notes and Places in News updates via UPSC Course Zone portal.',
    isSyncedToGoogle: false,
    completed: false
  },
  {
    id: 'plan-3',
    title: '📈 GS-3 Economy: Mrunal Sir PCB 15/16 Handout Revision',
    subject: 'GS-3 Economy',
    date: '2026-10-03',
    startTime: '14:30',
    endTime: '17:00',
    description: 'Monetary policy, RBI rate cut transmission, and external sector balance of payments.',
    isSyncedToGoogle: false,
    completed: false
  },
  {
    id: 'plan-4',
    title: '✍️ Mains Answer Writing: GS-4 Ethics Case Studies (2 Answers)',
    subject: 'GS-4 Ethics',
    date: '2026-10-03',
    startTime: '18:00',
    endTime: '19:30',
    description: 'Write 2 case studies on civil services code of conduct and submit to Professor AI Evaluator.',
    isSyncedToGoogle: false,
    completed: false
  },
  {
    id: 'plan-5',
    title: '🎯 CSAT Paper II: Reading Comprehension & Syllogism Drill',
    subject: 'CSAT',
    date: '2026-10-04',
    startTime: '16:00',
    endTime: '18:00',
    description: '30 CSAT PYQs with strict 2-hour timer to ensure >66 marks cutoff safety margin.',
    isSyncedToGoogle: false,
    completed: false
  }
];

export const KEY_MILESTONES = [
  {
    title: '🇮🇳 UPSC CSE Prelims 2027 Examination',
    date: '2027-05-23',
    startTime: '09:30',
    endTime: '16:30',
    description: 'D-Day: General Studies Paper 1 (09:30 - 11:30) & CSAT Paper 2 (14:30 - 16:30).'
  },
  {
    title: '📚 Complete GS Foundation Syllabus Coverage Milestone',
    date: '2026-12-31',
    startTime: '10:00',
    endTime: '18:00',
    description: 'Finish all core GS static subjects (Polity, History, Geography, Economy, Environment).'
  },
  {
    title: '📗 Optional Subject First Complete Revision Round',
    date: '2027-01-31',
    startTime: '09:00',
    endTime: '17:00',
    description: 'Complete Paper 1 & Paper 2 revision with past 10-year question bank analysis.'
  },
  {
    title: '📝 Prelims Test Series: Phase 1 Simulation (30 Full Mocks)',
    date: '2027-03-01',
    startTime: '09:30',
    endTime: '11:30',
    description: 'Weekly full-length test series with negative marking analysis.'
  }
];

export default function CalendarPlanner() {
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [calendarToken, setCalendarToken] = useState<string | null>(null);
  const [isSigningIn, setIsSigningIn] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  // Study plans state
  const [studyPlans, setStudyPlans] = useState<StudyPlanItem[]>(() => {
    try {
      const saved = localStorage.getItem('upsc_study_plans');
      if (saved) return JSON.parse(saved);
    } catch {}
    return DEFAULT_UPSC_PLANS;
  });

  // Google Calendar Live Events
  const [googleEvents, setGoogleEvents] = useState<GoogleCalendarItem[]>([]);
  const [loadingGoogleEvents, setLoadingGoogleEvents] = useState(false);
  const [calendarSyncFeedback, setCalendarSyncFeedback] = useState<string | null>(null);

  // Form State for new study session
  const [newTitle, setNewTitle] = useState('');
  const [newSubject, setNewSubject] = useState('GS-1');
  const [newDate, setNewDate] = useState(() => new Date().toISOString().split('T')[0]);
  const [newStartTime, setNewStartTime] = useState('08:00');
  const [newEndTime, setNewEndTime] = useState('10:00');
  const [newDesc, setNewDesc] = useState('');
  const [autoSyncToGoogle, setAutoSyncToGoogle] = useState(false);
  const [isAddingPlan, setIsAddingPlan] = useState(false);

  // Modal Confirmation State (Mandatory for Google Calendar mutative actions)
  const [confirmModal, setConfirmModal] = useState<{
    isOpen: boolean;
    title: string;
    message: string;
    confirmLabel: string;
    isDestructive: boolean;
    onConfirm: () => Promise<void>;
  }>({
    isOpen: false,
    title: '',
    message: '',
    confirmLabel: 'Confirm',
    isDestructive: false,
    onConfirm: async () => {}
  });

  // Save to localStorage whenever study plans change
  useEffect(() => {
    try {
      localStorage.setItem('upsc_study_plans', JSON.stringify(studyPlans));
    } catch {}
  }, [studyPlans]);

  // Auth listener
  useEffect(() => {
    const unsubscribe = initAuth(
      (user, token) => {
        setCurrentUser(user);
        setCalendarToken(token || getCalendarAccessToken());
      },
      () => {
        setCurrentUser(null);
        setCalendarToken(null);
      }
    );
    return () => unsubscribe();
  }, []);

  // When token is available, automatically load Google Calendar events
  useEffect(() => {
    if (calendarToken) {
      loadGoogleEvents(calendarToken);
    }
  }, [calendarToken]);

  const loadGoogleEvents = async (token: string) => {
    setLoadingGoogleEvents(true);
    setCalendarSyncFeedback(null);
    try {
      const items = await fetchGoogleCalendarEvents(token);
      setGoogleEvents(items);
    } catch (err: any) {
      console.warn("Failed to load calendar events:", err);
      // If unauthorized, token expired
      if (err.message && err.message.includes('401')) {
        setCalendarToken(null);
      }
    } finally {
      setLoadingGoogleEvents(false);
    }
  };

  const handleConnectGoogle = async () => {
    setIsSigningIn(true);
    setAuthError(null);
    try {
      const result = await signInWithGoogleCalendar();
      setCurrentUser(result.user);
      setCalendarToken(result.accessToken);
      if (result.accessToken) {
        await loadGoogleEvents(result.accessToken);
        setCalendarSyncFeedback("✅ Google Calendar connected! You can now sync your timetable.");
      }
    } catch (err: any) {
      console.error("Google Calendar sign-in error:", err);
      if (err.code === 'auth/popup-closed-by-user') {
        setAuthError("Sign-in cancelled. You can retry whenever you want to sync with Google Calendar.");
      } else {
        setAuthError(err.message || "Failed to connect to Google Calendar.");
      }
    } finally {
      setIsSigningIn(false);
    }
  };

  const handleDisconnectGoogle = async () => {
    setConfirmModal({
      isOpen: true,
      title: "Disconnect Google Calendar?",
      message: "This will disconnect your Google Calendar access from this session. Your local study timetable will remain intact.",
      confirmLabel: "Disconnect",
      isDestructive: true,
      onConfirm: async () => {
        await logOutGoogle();
        setCurrentUser(null);
        setCalendarToken(null);
        setGoogleEvents([]);
        setCalendarSyncFeedback("Google Calendar disconnected.");
        setConfirmModal(prev => ({ ...prev, isOpen: false }));
      }
    });
  };

  // Sync a single study plan to Google Calendar
  const handleSyncPlanToGoogle = (plan: StudyPlanItem) => {
    if (!calendarToken) {
      setAuthError("Please connect your Google Calendar first using the button above.");
      return;
    }

    setConfirmModal({
      isOpen: true,
      title: "Sync Study Session to Google Calendar?",
      message: `Add "${plan.title}" on ${plan.date} (${plan.startTime} - ${plan.endTime}) to your Google Calendar?`,
      confirmLabel: "Sync to Calendar",
      isDestructive: false,
      onConfirm: async () => {
        setConfirmModal(prev => ({ ...prev, isOpen: false }));
        try {
          const startDateTime = new Date(`${plan.date}T${plan.startTime}:00`).toISOString();
          const endDateTime = new Date(`${plan.date}T${plan.endTime}:00`).toISOString();

          const payload: CalendarEventPayload = {
            summary: plan.title,
            description: `${plan.description}\n\nSubject: ${plan.subject}\nTarget Exam: UPSC CSE 2027\nCreated via: UPSC Course Zone LMS Portal`,
            start: { dateTime: startDateTime },
            end: { dateTime: endDateTime },
            reminders: {
              useDefault: false,
              overrides: [
                { method: 'popup', minutes: 15 },
                { method: 'email', minutes: 60 }
              ]
            }
          };

          const created = await createGoogleCalendarEvent(calendarToken, payload);
          setStudyPlans(prev => prev.map(p => p.id === plan.id ? { ...p, isSyncedToGoogle: true, googleEventId: created.id } : p));
          setCalendarSyncFeedback(`✅ Added "${plan.title}" to your Google Calendar!`);
          loadGoogleEvents(calendarToken);
        } catch (err: any) {
          setCalendarSyncFeedback(`⚠️ Failed to sync: ${err.message}`);
        }
      }
    });
  };

  // Sync All UPSC Prelims 2027 Milestones
  const handleSyncMilestones = () => {
    if (!calendarToken) {
      setAuthError("Please connect your Google Calendar first to sync UPSC milestones.");
      return;
    }

    setConfirmModal({
      isOpen: true,
      title: "Sync UPSC 2027 Milestones?",
      message: `Do you want to add 4 strategic UPSC 2026-2027 preparation milestones (including Prelims 2027 Exam Date on 23 May 2027) directly to your Google Calendar?`,
      confirmLabel: "Sync All Milestones",
      isDestructive: false,
      onConfirm: async () => {
        setConfirmModal(prev => ({ ...prev, isOpen: false }));
        setCalendarSyncFeedback("⏳ Syncing milestones to Google Calendar...");
        try {
          let count = 0;
          for (const m of KEY_MILESTONES) {
            const startDateTime = new Date(`${m.date}T${m.startTime}:00`).toISOString();
            const endDateTime = new Date(`${m.date}T${m.endTime}:00`).toISOString();
            await createGoogleCalendarEvent(calendarToken, {
              summary: m.title,
              description: `${m.description}\n\nStrategic UPSC Prep Milestone\nMission Mussoorie 🇮🇳`,
              start: { dateTime: startDateTime },
              end: { dateTime: endDateTime }
            });
            count++;
          }
          setCalendarSyncFeedback(`🎉 Successfully synced ${count} UPSC milestones to your Google Calendar!`);
          loadGoogleEvents(calendarToken);
        } catch (err: any) {
          setCalendarSyncFeedback(`⚠️ Milestone sync interrupted: ${err.message}`);
        }
      }
    });
  };

  // Delete Google Calendar Event
  const handleDeleteGoogleEvent = (event: GoogleCalendarItem) => {
    if (!calendarToken) return;

    setConfirmModal({
      isOpen: true,
      title: "Delete Google Calendar Event?",
      message: `Are you sure you want to delete "${event.summary}" from your Google Calendar? This action cannot be undone.`,
      confirmLabel: "Delete from Calendar",
      isDestructive: true,
      onConfirm: async () => {
        setConfirmModal(prev => ({ ...prev, isOpen: false }));
        try {
          await deleteGoogleCalendarEvent(calendarToken, event.id);
          setCalendarSyncFeedback(`🗑️ Deleted "${event.summary}" from Google Calendar.`);
          // Also unmark locally if linked
          setStudyPlans(prev => prev.map(p => p.googleEventId === event.id ? { ...p, isSyncedToGoogle: false, googleEventId: undefined } : p));
          loadGoogleEvents(calendarToken);
        } catch (err: any) {
          setCalendarSyncFeedback(`⚠️ Could not delete: ${err.message}`);
        }
      }
    });
  };

  // Add new custom study slot
  const handleAddPlan = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;

    const newPlan: StudyPlanItem = {
      id: `plan-${Date.now()}`,
      title: newTitle.trim(),
      subject: newSubject,
      date: newDate,
      startTime: newStartTime,
      endTime: newEndTime,
      description: newDesc.trim() || `${newSubject} revision study session.`,
      isSyncedToGoogle: false,
      completed: false
    };

    if (autoSyncToGoogle && calendarToken) {
      setConfirmModal({
        isOpen: true,
        title: "Add & Sync to Google Calendar?",
        message: `Create this study session and immediately sync it to your Google Calendar for ${newDate} (${newStartTime} - ${newEndTime})?`,
        confirmLabel: "Create & Sync",
        isDestructive: false,
        onConfirm: async () => {
          setConfirmModal(prev => ({ ...prev, isOpen: false }));
          try {
            const startDateTime = new Date(`${newDate}T${newStartTime}:00`).toISOString();
            const endDateTime = new Date(`${newDate}T${newEndTime}:00`).toISOString();
            const created = await createGoogleCalendarEvent(calendarToken, {
              summary: newPlan.title,
              description: newPlan.description,
              start: { dateTime: startDateTime },
              end: { dateTime: endDateTime }
            });
            newPlan.isSyncedToGoogle = true;
            newPlan.googleEventId = created.id;
            setStudyPlans(prev => [newPlan, ...prev]);
            loadGoogleEvents(calendarToken);
            setCalendarSyncFeedback(`✅ Added "${newPlan.title}" and synced to Google Calendar!`);
          } catch {
            setStudyPlans(prev => [newPlan, ...prev]);
          }
          resetForm();
        }
      });
    } else {
      setStudyPlans(prev => [newPlan, ...prev]);
      resetForm();
    }
  };

  const resetForm = () => {
    setNewTitle('');
    setNewDesc('');
    setIsAddingPlan(false);
  };

  const handleDeleteLocalPlan = (id: string) => {
    setStudyPlans(prev => prev.filter(p => p.id !== id));
  };

  const handleToggleComplete = (id: string) => {
    setStudyPlans(prev => prev.map(p => p.id === id ? { ...p, completed: !p.completed } : p));
  };

  return (
    <div className="space-y-6">
      {/* Top Banner: Zero-Friction Notice & Calendar Header */}
      <div className="bg-gradient-to-r from-blue-900 via-indigo-900 to-slate-900 text-white rounded-2xl p-5 md:p-6 shadow-xl border border-blue-800/40 relative overflow-hidden">
        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1.5">
              <span className="bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-xs font-semibold px-2.5 py-0.5 rounded-full flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                Zero Forced Login
              </span>
              <span className="bg-blue-500/20 text-blue-300 border border-blue-500/30 text-xs font-medium px-2.5 py-0.5 rounded-full">
                Google Calendar Integration
              </span>
            </div>
            <h2 className="text-xl md:text-2xl font-bold tracking-tight text-white flex items-center gap-2">
              <CalendarIcon className="w-6 h-6 text-sky-400" />
              UPSC Study Planner & Google Calendar
            </h2>
            <p className="text-sm text-slate-300 mt-1 max-w-2xl">
              Organize your daily GS, CSAT, and Optional study slots. Sync your schedule to your personal 
              Google Calendar with 1-click reminders so you never miss a revision milestone.
            </p>
          </div>

          {/* Google Auth Status & Action */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5 bg-slate-800/80 p-3 rounded-xl border border-slate-700/60 backdrop-blur-sm">
            {currentUser && calendarToken ? (
              <div className="flex items-center justify-between sm:justify-start gap-3">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-full bg-emerald-600/30 border border-emerald-400 flex items-center justify-center text-xs font-bold text-emerald-300">
                    {currentUser.displayName ? currentUser.displayName.slice(0, 2).toUpperCase() : 'GC'}
                  </div>
                  <div className="text-left text-xs">
                    <div className="font-semibold text-emerald-400 flex items-center gap-1">
                      <CheckCircle className="w-3.5 h-3.5" /> Connected
                    </div>
                    <div className="text-slate-300 truncate max-w-[150px]">{currentUser.email}</div>
                  </div>
                </div>
                <button
                  onClick={handleDisconnectGoogle}
                  title="Disconnect Google Calendar"
                  className="p-1.5 text-slate-400 hover:text-rose-400 rounded-lg hover:bg-slate-700/50 transition-colors"
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <div className="flex flex-col gap-1.5">
                <button
                  onClick={handleConnectGoogle}
                  disabled={isSigningIn}
                  className="flex items-center justify-center gap-2.5 px-4 py-2 bg-white hover:bg-slate-50 text-slate-800 text-xs font-semibold rounded-lg shadow-sm border border-slate-300 transition-all hover:shadow active:scale-[0.98]"
                >
                  {/* Official Google G Logo */}
                  <svg className="w-4 h-4 shrink-0" viewBox="0 0 48 48">
                    <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
                    <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
                    <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
                    <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
                  </svg>
                  <span>{isSigningIn ? 'Connecting...' : 'Connect Google Calendar'}</span>
                </button>
                <span className="text-[10px] text-slate-400 text-center">
                  Optional: Only needed for Calendar sync
                </span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Notifications & Feedback */}
      {calendarSyncFeedback && (
        <div className="bg-sky-50 border border-sky-200 text-sky-900 text-xs md:text-sm px-4 py-2.5 rounded-xl flex items-center justify-between animate-fadeIn">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-sky-600 shrink-0" />
            <span>{calendarSyncFeedback}</span>
          </div>
          <button onClick={() => setCalendarSyncFeedback(null)} className="text-sky-600 hover:text-sky-800 text-xs font-semibold">
            Dismiss
          </button>
        </div>
      )}

      {authError && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 text-xs md:text-sm px-4 py-2.5 rounded-xl flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{authError}</span>
          </div>
          <button onClick={() => setAuthError(null)} className="text-rose-600 hover:text-rose-800 text-xs font-semibold">
            Dismiss
          </button>
        </div>
      )}

      {/* Quick Action Toolbar */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <button
          onClick={() => setIsAddingPlan(!isAddingPlan)}
          className="flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white font-medium text-xs md:text-sm py-2.5 px-4 rounded-xl shadow-sm transition-all"
        >
          <Plus className="w-4 h-4" />
          {isAddingPlan ? 'Close Slot Form' : 'Add Study Session'}
        </button>

        <button
          onClick={handleSyncMilestones}
          className="flex items-center justify-center gap-2 bg-white hover:bg-slate-50 text-slate-800 border border-slate-300 font-medium text-xs md:text-sm py-2.5 px-4 rounded-xl shadow-sm transition-all"
        >
          <CalendarCheck className="w-4 h-4 text-indigo-600" />
          Sync UPSC 2027 Milestones
        </button>

        <button
          onClick={() => calendarToken ? loadGoogleEvents(calendarToken) : handleConnectGoogle()}
          className="flex items-center justify-center gap-2 bg-white hover:bg-slate-50 text-slate-800 border border-slate-300 font-medium text-xs md:text-sm py-2.5 px-4 rounded-xl shadow-sm transition-all"
        >
          <RefreshCw className={`w-4 h-4 text-sky-600 ${loadingGoogleEvents ? 'animate-spin' : ''}`} />
          {calendarToken ? 'Refresh Google Calendar' : 'Connect Calendar'}
        </button>
      </div>

      {/* Add Study Slot Form Modal/Collapse */}
      {isAddingPlan && (
        <form onSubmit={handleAddPlan} className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
              <Clock className="w-4 h-4 text-indigo-600" />
              Schedule New Study Slot
            </h3>
            <span className="text-xs text-slate-500">Plan your timetable</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Session Title</label>
              <input
                type="text"
                required
                placeholder="e.g. GS-1 Modern History: 1857 Revolt Spectrum Ch 5"
                value={newTitle}
                onChange={e => setNewTitle(e.target.value)}
                className="w-full text-xs md:text-sm px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Subject Focus</label>
              <select
                value={newSubject}
                onChange={e => setNewSubject(e.target.value)}
                className="w-full text-xs md:text-sm px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none bg-white"
              >
                <option value="GS-1">GS-1 (History, Geography, Society)</option>
                <option value="GS-2">GS-2 (Polity, Governance, IR)</option>
                <option value="GS-3">GS-3 (Economy, Env, Science & Tech)</option>
                <option value="GS-4">GS-4 (Ethics, Integrity & Case Studies)</option>
                <option value="Current Affairs">Current Affairs (The Hindu / PIB)</option>
                <option value="Optional">Optional Subject</option>
                <option value="CSAT">CSAT Paper II Practice</option>
                <option value="Mock Test">Mock Test / Answer Evaluation</option>
              </select>
            </div>

            <div className="grid grid-cols-3 gap-2">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Date</label>
                <input
                  type="date"
                  value={newDate}
                  onChange={e => setNewDate(e.target.value)}
                  className="w-full text-xs px-2 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Start Time</label>
                <input
                  type="time"
                  value={newStartTime}
                  onChange={e => setNewStartTime(e.target.value)}
                  className="w-full text-xs px-2 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">End Time</label>
                <input
                  type="time"
                  value={newEndTime}
                  onChange={e => setNewEndTime(e.target.value)}
                  className="w-full text-xs px-2 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Notes / Target Chapters</label>
              <input
                type="text"
                placeholder="Specific handouts, pages, or PYQs to solve..."
                value={newDesc}
                onChange={e => setNewDesc(e.target.value)}
                className="w-full text-xs md:text-sm px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              />
            </div>
          </div>

          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pt-2">
            <label className="flex items-center gap-2 cursor-pointer text-xs text-slate-700">
              <input
                type="checkbox"
                checked={autoSyncToGoogle}
                disabled={!calendarToken}
                onChange={e => setAutoSyncToGoogle(e.target.checked)}
                className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
              />
              <span>Also add directly to my Google Calendar {calendarToken ? '' : '(Connect Google first)'}</span>
            </label>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={resetForm}
                className="px-3 py-1.5 text-xs text-slate-600 hover:text-slate-800 font-medium"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-lg shadow-sm"
              >
                Save Study Slot
              </button>
            </div>
          </div>
        </form>
      )}

      {/* Main Grid: Study Timetable & Google Calendar Live Events */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Columns: Study Timetable Slots */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
              <BookOpen className="w-4 h-4 text-indigo-600" />
              Daily Study Timetable ({studyPlans.length} Slots)
            </h3>
            <span className="text-xs text-slate-500">
              {studyPlans.filter(p => p.completed).length} completed • {studyPlans.filter(p => p.isSyncedToGoogle).length} synced
            </span>
          </div>

          <div className="space-y-3">
            {studyPlans.map(plan => (
              <div
                key={plan.id}
                className={`bg-white border rounded-xl p-4 transition-all hover:shadow-md ${
                  plan.completed
                    ? 'border-emerald-200 bg-emerald-50/20 opacity-75'
                    : 'border-slate-200 shadow-sm'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 border border-indigo-200">
                        {plan.subject}
                      </span>
                      <span className="text-xs text-slate-500 flex items-center gap-1 font-mono">
                        <Clock className="w-3 h-3 text-slate-400" />
                        {plan.date} • {plan.startTime} - {plan.endTime}
                      </span>
                      {plan.isSyncedToGoogle && (
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 flex items-center gap-1">
                          <CheckCircle className="w-3 h-3" /> Synced to Google
                        </span>
                      )}
                    </div>

                    <h4 className={`text-sm font-bold ${plan.completed ? 'line-through text-slate-500' : 'text-slate-900'}`}>
                      {plan.title}
                    </h4>

                    {plan.description && (
                      <p className="text-xs text-slate-600 line-clamp-2 leading-relaxed">
                        {plan.description}
                      </p>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-1.5 shrink-0">
                    <button
                      onClick={() => handleToggleComplete(plan.id)}
                      title={plan.completed ? "Mark incomplete" : "Mark completed"}
                      className={`p-1.5 rounded-lg border text-xs transition-colors ${
                        plan.completed
                          ? 'border-emerald-300 bg-emerald-100 text-emerald-700'
                          : 'border-slate-200 hover:bg-slate-100 text-slate-600'
                      }`}
                    >
                      <CheckCircle className="w-4 h-4" />
                    </button>

                    {!plan.isSyncedToGoogle && (
                      <button
                        onClick={() => handleSyncPlanToGoogle(plan)}
                        title="Sync to Google Calendar"
                        className="p-1.5 rounded-lg border border-sky-200 bg-sky-50 text-sky-700 hover:bg-sky-100 text-xs transition-colors"
                      >
                        <CalendarIcon className="w-4 h-4" />
                      </button>
                    )}

                    <button
                      onClick={() => handleDeleteLocalPlan(plan.id)}
                      title="Delete slot"
                      className="p-1.5 rounded-lg border border-slate-200 hover:border-rose-200 hover:bg-rose-50 text-slate-400 hover:text-rose-600 text-xs transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right 1 Column: Google Calendar Live Agenda & Milestones */}
        <div className="space-y-6">
          {/* Key Milestones Card */}
          <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <h4 className="text-xs font-bold text-slate-900 flex items-center gap-1.5 uppercase tracking-wider">
                <Sparkles className="w-3.5 h-3.5 text-amber-500" />
                UPSC 2027 Key Milestones
              </h4>
              <button
                onClick={handleSyncMilestones}
                className="text-[11px] font-semibold text-indigo-600 hover:text-indigo-800"
              >
                Sync All
              </button>
            </div>

            <div className="space-y-2.5">
              {KEY_MILESTONES.map((m, idx) => (
                <div key={idx} className="p-2.5 rounded-lg bg-slate-50 border border-slate-100 text-xs space-y-1">
                  <div className="font-semibold text-slate-900">{m.title}</div>
                  <div className="text-[11px] text-slate-500 flex items-center gap-2 font-mono">
                    <span>📅 {m.date}</span>
                    <span>⏰ {m.startTime}</span>
                  </div>
                  <div className="text-[11px] text-slate-600 line-clamp-1">{m.description}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Live Google Calendar Events Card */}
          <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <h4 className="text-xs font-bold text-slate-900 flex items-center gap-1.5 uppercase tracking-wider">
                <CalendarIcon className="w-3.5 h-3.5 text-sky-600" />
                Live Google Calendar Events
              </h4>
              {calendarToken && (
                <button
                  onClick={() => loadGoogleEvents(calendarToken)}
                  disabled={loadingGoogleEvents}
                  className="text-slate-400 hover:text-slate-600"
                  title="Refresh"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${loadingGoogleEvents ? 'animate-spin' : ''}`} />
                </button>
              )}
            </div>

            {!calendarToken ? (
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-center space-y-2.5">
                <CalendarIcon className="w-8 h-8 text-slate-300 mx-auto" />
                <div className="text-xs text-slate-600">
                  Connect your Google Calendar to view upcoming events and sync your UPSC study schedule.
                </div>
                <button
                  onClick={handleConnectGoogle}
                  disabled={isSigningIn}
                  className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg shadow-sm"
                >
                  <CalendarCheck className="w-3.5 h-3.5" />
                  Connect Now
                </button>
              </div>
            ) : loadingGoogleEvents ? (
              <div className="p-6 text-center text-xs text-slate-500 space-y-2">
                <RefreshCw className="w-5 h-5 text-indigo-500 animate-spin mx-auto" />
                <div>Fetching Google Calendar events...</div>
              </div>
            ) : googleEvents.length === 0 ? (
              <div className="p-4 text-center text-xs text-slate-500">
                No upcoming events found on your Google Calendar for this month.
              </div>
            ) : (
              <div className="space-y-2 max-h-[360px] overflow-y-auto pr-1">
                {googleEvents.map(evt => {
                  const startTime = evt.start?.dateTime || evt.start?.date;
                  const dateStr = startTime ? new Date(startTime).toLocaleString('en-IN', {
                    month: 'short',
                    day: 'numeric',
                    hour: evt.start?.dateTime ? '2-digit' : undefined,
                    minute: evt.start?.dateTime ? '2-digit' : undefined
                  }) : 'All Day';

                  return (
                    <div
                      key={evt.id}
                      className="p-2.5 rounded-lg bg-sky-50/50 border border-sky-100 hover:border-sky-200 transition-all text-xs flex items-start justify-between gap-2"
                    >
                      <div className="space-y-0.5 flex-1 min-w-0">
                        <div className="font-semibold text-slate-900 truncate" title={evt.summary}>
                          {evt.summary}
                        </div>
                        <div className="text-[11px] text-sky-700 font-mono">
                          {dateStr}
                        </div>
                      </div>

                      <div className="flex items-center gap-1 shrink-0">
                        {evt.htmlLink && (
                          <a
                            href={evt.htmlLink}
                            target="_blank"
                            rel="noreferrer"
                            className="p-1 text-slate-400 hover:text-sky-600 rounded"
                            title="Open in Google Calendar"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                          </a>
                        )}
                        <button
                          onClick={() => handleDeleteGoogleEvent(evt)}
                          className="p-1 text-slate-400 hover:text-rose-600 rounded"
                          title="Delete from Google Calendar"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Mandatory User Confirmation Modal for Workspace API operations */}
      {confirmModal.isOpen && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4 animate-fadeIn">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-200 space-y-4 animate-scaleUp">
            <div className="flex items-center gap-3">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
                confirmModal.isDestructive ? 'bg-rose-100 text-rose-600' : 'bg-indigo-100 text-indigo-600'
              }`}>
                {confirmModal.isDestructive ? <AlertCircle className="w-5 h-5" /> : <CalendarCheck className="w-5 h-5" />}
              </div>
              <h3 className="text-base font-bold text-slate-900">{confirmModal.title}</h3>
            </div>

            <p className="text-sm text-slate-600 leading-relaxed">
              {confirmModal.message}
            </p>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setConfirmModal(prev => ({ ...prev, isOpen: false }))}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 rounded-lg hover:bg-slate-100 transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmModal.onConfirm}
                className={`px-4 py-2 text-xs font-semibold text-white rounded-lg shadow-sm transition-colors ${
                  confirmModal.isDestructive
                    ? 'bg-rose-600 hover:bg-rose-700'
                    : 'bg-indigo-600 hover:bg-indigo-700'
                }`}
              >
                {confirmModal.confirmLabel}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
