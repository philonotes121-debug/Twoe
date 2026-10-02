import { app, initializeTelegramBot } from '../server';

let initialization: Promise<void> | undefined;

export default async function handler(request: any, response: any) {
  if (!initialization) {
    initialization = initializeTelegramBot();
  }

  try {
    await initialization;
  } catch (error) {
    console.error('Telegram bootstrap failed:', error);
  }

  return app(request, response);
}
