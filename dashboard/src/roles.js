// Stable stored role values, shared by navigation and account management.
export const ROLE_TITLES = Object.freeze({
  admin: 'Системний адміністратор',
  shop_admin: 'Адміністратор',
  operator: 'Менеджер',
})
export const isAdministrativeRole = (role) => role === 'admin' || role === 'shop_admin'
// Catalog changes (prices, publication, stock, import, removal) are administrative.
export const canManageCatalog = (role) => isAdministrativeRole(role)
export const canManageAccount = (role, targetRole) => role === 'admin' || (role === 'shop_admin' && targetRole === 'operator')
export const assignableRoles = (role) => role === 'admin' ? ['operator', 'shop_admin'] : role === 'shop_admin' ? ['operator'] : []
export function canAccessPage(role, pathname) {
  if (!Object.hasOwn(ROLE_TITLES, role)) return false
  try { pathname = decodeURIComponent(String(pathname)).toLowerCase() } catch { return false }
  if (/^\/(logs|backups)(\/|$)/.test(pathname)) return role === 'admin'
  // Marketing is administrative (A10); managers keep sales, customers, support and catalog reading.
  if (/^\/(settings|operators|blog|documents|promos|broadcasts)(\/|$)/.test(pathname)) return isAdministrativeRole(role)
  return true
}
export function filterSettingGroups(groups, allowedKeys = []) {
  const allowed = new Set(allowedKeys)
  return groups.map((group) => ({ ...group,
    toggle: allowed.has(group.toggle) ? group.toggle : undefined,
    items: group.items.filter((item) => allowed.has(item.key)),
  })).filter((group) => group.toggle || group.items.length)
}
