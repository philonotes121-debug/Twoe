export interface SectionItem {
  key: string;
  name: string;
  icon: string;
  parent_id?: string | null;
}

export const SECTIONS: SectionItem[] = [
  { key: 'upsc_foundation', name: 'GS Foundation', icon: '🏛️' },
  { key: 'upsc_optional', name: 'Optional Subjects', icon: '📗' },
  { key: 'optional_history', name: 'History Optional', icon: '📜', parent_id: 'upsc_optional' },
  { key: 'optional_psir', name: 'PSIR Optional', icon: '🌐', parent_id: 'upsc_optional' },
  { key: 'optional_anthropology', name: 'Anthropology Optional', icon: '🧬', parent_id: 'upsc_optional' },
  { key: 'optional_geography', name: 'Geography Optional', icon: '🗺️', parent_id: 'upsc_optional' },
  { key: 'optional_sociology', name: 'Sociology Optional', icon: '👥', parent_id: 'upsc_optional' },
  { key: 'test_series', name: 'Test Series', icon: '📝' },
  { key: 'state_psc', name: 'State PSC', icon: '🏢' },
  { key: 'bpsc', name: 'BPSC', icon: '📍', parent_id: 'state_psc' },
  { key: 'combo', name: 'Combo Deals', icon: '🎁' }
];