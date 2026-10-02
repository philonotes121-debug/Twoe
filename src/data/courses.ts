export interface CourseItem {
  id: number;
  name: string;
  faculty: string;
  medium: string;
  notes: string;
  price: number;
  batch_id: string;
  section_keys: string[];
}

export const COURSES: CourseItem[] = [
  {
    id: 218,
    name: 'Economy PCB 15/16',
    faculty: 'Mrunal',
    medium: 'Both',
    notes: 'Economy course listing. Confirm current availability and inclusions before payment.',
    price: 300,
    batch_id: 'CSE-218',
    section_keys: ['upsc_foundation']
  },
  {
    id: 152,
    name: 'GS Foundation 2027',
    faculty: 'Forum IAS',
    medium: 'Both',
    notes: 'GS Foundation course listing. Confirm current availability and inclusions before payment.',
    price: 1200,
    batch_id: 'CSE-152',
    section_keys: ['upsc_foundation']
  },
  {
    id: 69,
    name: 'History Optional 2027',
    faculty: 'Vision IAS',
    medium: 'English',
    notes: 'History Optional course listing. Confirm current availability and inclusions before payment.',
    price: 800,
    batch_id: 'CSE-069',
    section_keys: ['upsc_optional', 'optional_history']
  },
  {
    id: 158,
    name: 'Magna Carta Polity',
    faculty: 'Atish Mathur',
    medium: 'Both',
    notes: 'Polity course listing. Confirm current availability and inclusions before payment.',
    price: 500,
    batch_id: 'CSE-158',
    section_keys: ['upsc_foundation']
  },
  {
    id: 206,
    name: 'Environment 2026',
    faculty: 'Sudarshan Gujjar',
    medium: 'Both',
    notes: 'Environment course listing. Confirm current availability and inclusions before payment.',
    price: 200,
    batch_id: 'CSE-206',
    section_keys: ['upsc_foundation']
  }
];