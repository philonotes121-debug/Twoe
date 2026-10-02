import { initializeApp } from 'firebase/app';
import {
  getAuth,
  signInWithPopup,
  GoogleAuthProvider,
  onAuthStateChanged,
  User,
  signOut
} from 'firebase/auth';
import {
  getFirestore,
  doc,
  getDocFromServer,
  collection,
  query,
  where,
  getDocs,
  setDoc,
  deleteDoc,
  onSnapshot
} from 'firebase/firestore';
import firebaseConfig from '../firebase-applet-config.json';

// Initialize Firebase
export const app = initializeApp(firebaseConfig);
export const db = getFirestore(app, firebaseConfig.firestoreDatabaseId);
export const auth = getAuth(app);

// Provider with Google Calendar scopes
export const googleCalendarProvider = new GoogleAuthProvider();
googleCalendarProvider.addScope('https://www.googleapis.com/auth/calendar');
googleCalendarProvider.addScope('https://www.googleapis.com/auth/calendar.events');
googleCalendarProvider.setCustomParameters({
  prompt: 'consent'
});

// In-memory token storage (Do NOT store in localStorage or sessionStorage)
let cachedAccessToken: string | null = null;
let isSigningIn = false;

// Initialize connection test
export async function testFirestoreConnection() {
  try {
    await getDocFromServer(doc(db, 'test', 'connection'));
  } catch (error) {
    if (error instanceof Error && error.message.includes('the client is offline')) {
      console.warn("Firestore client is offline or starting up.");
    }
  }
}

// Structured error handling as required by Firebase Integration Skill
export enum OperationType {
  CREATE = 'create',
  UPDATE = 'update',
  DELETE = 'delete',
  LIST = 'list',
  GET = 'get',
  WRITE = 'write',
}

export interface FirestoreErrorInfo {
  error: string;
  operationType: OperationType;
  path: string | null;
  authInfo: {
    userId?: string | null;
    email?: string | null;
    emailVerified?: boolean | null;
    isAnonymous?: boolean | null;
    tenantId?: string | null;
    providerInfo?: {
      providerId?: string | null;
      email?: string | null;
    }[];
  };
}

export function handleFirestoreError(error: unknown, operationType: OperationType, path: string | null): never {
  const errInfo: FirestoreErrorInfo = {
    error: error instanceof Error ? error.message : String(error),
    authInfo: {
      userId: auth.currentUser?.uid,
      email: auth.currentUser?.email,
      emailVerified: auth.currentUser?.emailVerified,
      isAnonymous: auth.currentUser?.isAnonymous,
      tenantId: auth.currentUser?.tenantId,
      providerInfo: auth.currentUser?.providerData?.map(provider => ({
        providerId: provider.providerId,
        email: provider.email,
      })) || []
    },
    operationType,
    path
  };
  console.error('Firestore Error: ', JSON.stringify(errInfo));
  throw new Error(JSON.stringify(errInfo));
}

// Auth State Initializer
export const initAuth = (
  onAuthSuccess?: (user: User, token: string | null) => void,
  onAuthFailure?: () => void
) => {
  return onAuthStateChanged(auth, async (user: User | null) => {
    if (user) {
      if (onAuthSuccess) onAuthSuccess(user, cachedAccessToken);
    } else {
      cachedAccessToken = null;
      if (onAuthFailure) onAuthFailure();
    }
  });
};

// Sign in with Google (explicit user click)
export const signInWithGoogleCalendar = async (): Promise<{ user: User; accessToken: string | null }> => {
  try {
    isSigningIn = true;
    const result = await signInWithPopup(auth, googleCalendarProvider);
    const credential = GoogleAuthProvider.credentialFromResult(result);
    cachedAccessToken = credential?.accessToken || null;
    return { user: result.user, accessToken: cachedAccessToken };
  } catch (error: any) {
    console.error('Sign in error:', error);
    throw error;
  } finally {
    isSigningIn = false;
  }
};

export const getCalendarAccessToken = (): string | null => {
  return cachedAccessToken;
};

export const logOutGoogle = async () => {
  await signOut(auth);
  cachedAccessToken = null;
};

// -------------------------------------------------------------
// Google Calendar API Integration (Client-Side Bearer Token)
// -------------------------------------------------------------
export interface CalendarEventPayload {
  summary: string;
  description: string;
  start: {
    dateTime: string; // ISO 8601 string
    timeZone?: string;
  };
  end: {
    dateTime: string;
    timeZone?: string;
  };
  reminders?: {
    useDefault: boolean;
    overrides?: Array<{ method: string; minutes: number }>;
  };
}

export interface GoogleCalendarItem {
  id: string;
  summary: string;
  description?: string;
  start?: { dateTime?: string; date?: string };
  end?: { dateTime?: string; date?: string };
  htmlLink?: string;
}

// Fetch calendar events
export async function fetchGoogleCalendarEvents(token: string): Promise<GoogleCalendarItem[]> {
  const now = new Date();
  const timeMin = new Date(now.getFullYear(), now.getMonth(), 1).toISOString();
  const url = `https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=${encodeURIComponent(timeMin)}&singleEvents=true&orderBy=startTime&maxResults=50`;

  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/json'
    }
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.error?.message || `Failed to fetch events: ${res.statusText}`);
  }

  const data = await res.json();
  return data.items || [];
}

// Create calendar event (with user confirmation enforced in UI)
export async function createGoogleCalendarEvent(token: string, event: CalendarEventPayload): Promise<GoogleCalendarItem> {
  const url = `https://www.googleapis.com/calendar/v3/calendars/primary/events`;
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      Accept: 'application/json'
    },
    body: JSON.stringify(event)
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.error?.message || `Failed to create event: ${res.statusText}`);
  }

  return await res.json();
}

// Delete calendar event (destructive - requires confirmation dialog)
export async function deleteGoogleCalendarEvent(token: string, eventId: string): Promise<boolean> {
  const url = `https://www.googleapis.com/calendar/v3/calendars/primary/events/${encodeURIComponent(eventId)}`;
  const res = await fetch(url, {
    method: 'DELETE',
    headers: {
      Authorization: `Bearer ${token}`
    }
  });

  if (!res.ok && res.status !== 404 && res.status !== 204) {
    throw new Error(`Failed to delete event: ${res.statusText}`);
  }
  return true;
}
