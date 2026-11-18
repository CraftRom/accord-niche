// Imported first in main.jsx: runs before any module reads browser storage.
import { migrateLegacyStorage } from './storageKeys.js'

for (const name of ['localStorage', 'sessionStorage']) {
  try { migrateLegacyStorage(globalThis[name]) } catch { /* storage blocked */ }
}
