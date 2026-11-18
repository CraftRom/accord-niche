// Browser storage keys and in-page event names of the ACCORD dashboard
// (UI-029). The panel started as a fork of ELFAR and kept its `elfar:*`
// names; they are migrated once (storageMigration.js) so nothing a manager
// saved — chat drafts, notification settings, volume — is lost.
export const STORAGE = Object.freeze({
  notificationSettings: 'accord:notification-settings',
  notificationVolume: 'accord:notification-device-volume',
  notificationNudge: 'accord:notification-nudge-dismissed',
  notificationLeader: 'accord:notification-leader',
  chatDraftPrefix: 'accord:chat-draft:v1:',
  chunkReload: 'accord:chunk-reload',
})

export const EVENTS = Object.freeze({
  ordersChanged: 'accord:orders:changed',
  notificationsFresh: 'accord:notifications:fresh',
  supportRead: 'accord:support:read',
})

// Old key → new key. Prefixes move every key that starts with them.
export const LEGACY_KEYS = Object.freeze({
  'elfar:notification-settings': STORAGE.notificationSettings,
  'elfar:notification-device-volume': STORAGE.notificationVolume,
  'elfar:notification-nudge-dismissed': STORAGE.notificationNudge,
})
export const LEGACY_PREFIXES = Object.freeze({
  'elfar:chat-draft:v1:': STORAGE.chatDraftPrefix,
})
// Short-lived marks that are simply dropped.
export const LEGACY_DROP = Object.freeze(['elfar:notification-leader', 'elfar:chunk-reload'])

/**
 * Moves legacy values to the new keys. A value already present under the new
 * key wins (it is newer). Returns how many values moved. Never throws: storage
 * can be unavailable (private mode, blocked site data).
 */
export function migrateLegacyStorage(storage) {
  let moved = 0
  try {
    if (!storage) return 0
    const keys = Array.from({ length: storage.length }, (_, i) => storage.key(i)).filter(Boolean)
    for (const key of keys) {
      let target = LEGACY_KEYS[key]
      if (!target) {
        const prefix = Object.keys(LEGACY_PREFIXES).find((item) => key.startsWith(item))
        if (prefix) target = LEGACY_PREFIXES[prefix] + key.slice(prefix.length)
      }
      if (target) {
        const value = storage.getItem(key)
        if (storage.getItem(target) === null && value !== null) { storage.setItem(target, value); moved++ }
        storage.removeItem(key)
      } else if (LEGACY_DROP.includes(key)) {
        storage.removeItem(key)
      }
    }
  } catch { /* storage unavailable: nothing to migrate */ }
  return moved
}
