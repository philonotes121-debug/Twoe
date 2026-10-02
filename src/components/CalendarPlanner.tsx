import React, { useState, useEffect } from 'react';
import {
  Calendar as CalendarIcon,
  Clock,
  Plus,
  Trash2,
  CheckCircle,
  Sparkles,
  BookOpen
} from 'lucide-react';

export interface StudyPlanItem {
  id: string;
  title: string;
  subject: string;
  date: string;
  startTime: string;
  endTime: string;
  description: string;
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
  // Study plans state
  const [studyPlans, setStudyPlans] = useState<StudyPlanItem[]>(() => {
    try {
      const saved = localStorage.getItem('upsc_study_plans');
      if (saved) return JSON.parse(saved);
    } catch {}
    return DEFAULT_UPSC_PLANS;
  });

  // Form State for new study session
  const [newTitle, setNewTitle] = useState('');
  const [newSubject, setNewSubject] = useState('GS-1');
  const [newDate, setNewDate] = useState(() => new Date().toISOString().split('T')[0]);
  const [newStartTime, setNewStartTime] = useState('08:00');
  const [newEndTime, setNewEndTime] = useState('10:00');
  const [newDesc, setNewDesc] = useState('');
  const [isAddingPlan, setIsAddingPlan] = useState(false);

  // Save to localStorage whenever study plans change
  useEffect(() => {
    try {
      localStorage.setItem('upsc_study_plans', JSON.stringify(studyPlans));
    } catch {}
  }, [studyPlans]);

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
      completed: false
    };

    setStudyPlans(prev => [newPlan, ...prev]);
    resetForm();
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
      <div className="bg-slate-950 text-white rounded-xl p-5 border border-slate-800">
        <h2 className="text-xl font-bold flex items-center gap-2">
          <CalendarIcon className="w-5 h-5 text-sky-400" />
          UPSC Study Planner
        </h2>
        <p className="text-sm text-slate-400 mt-1">Study plans are saved in this browser. No external account is required.</p>
      </div>

      {/* Quick Action Toolbar */}
      <div className="grid grid-cols-1 gap-3">
        <button
          onClick={() => setIsAddingPlan(!isAddingPlan)}
          className="flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white font-medium text-xs md:text-sm py-2.5 px-4 rounded-xl shadow-sm transition-all"
        >
          <Plus className="w-4 h-4" />
          {isAddingPlan ? 'Close Slot Form' : 'Add Study Session'}
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

          <div className="flex items-center justify-end gap-2 pt-2">
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

      {/* Main Grid: Study Timetable & Key Milestones */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Columns: Study Timetable Slots */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
              <BookOpen className="w-4 h-4 text-indigo-600" />
              Daily Study Timetable ({studyPlans.length} Slots)
            </h3>
            <span className="text-xs text-slate-500">
              {studyPlans.filter(p => p.completed).length} completed
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

        {/* Right 1 Column: Key Milestones */}
        <div className="space-y-6">
          {/* Key Milestones Card */}
          <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <h4 className="text-xs font-bold text-slate-900 flex items-center gap-1.5 uppercase tracking-wider">
                <Sparkles className="w-3.5 h-3.5 text-amber-500" />
                UPSC 2027 Key Milestones
              </h4>
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

        </div>
      </div>

    </div>
  );
}
