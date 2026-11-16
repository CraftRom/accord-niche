import test from 'node:test'
import assert from 'node:assert/strict'
import { canAccessPage, canManageAccount, assignableRoles, filterSettingGroups } from '../src/roles.js'

test('manager direct routes deny settings, team and infrastructure', () => {
  for (const path of ['/settings', '/SETTINGS', '/%73ettings', '/settings/security', '/operators', '/operators/5', '/logs', '/backups', '/blog', '/BLOG', '/%62log', '/blog/5']) {
    assert.equal(canAccessPage('operator', path), false, path)
  }
  for (const path of ['/orders', '/orders/12', '/support', '/customers', '/catalog']) assert.equal(canAccessPage('operator', path), true, path)
})
test('administrator retains store settings but cannot enter infrastructure', () => {
  for (const path of ['/settings', '/operators', '/orders', '/blog']) assert.equal(canAccessPage('shop_admin', path), true)
  for (const path of ['/logs', '/backups']) assert.equal(canAccessPage('shop_admin', path), false)
  for (const path of ['/settings', '/operators', '/logs', '/backups']) assert.equal(canAccessPage('admin', path), true)
  assert.equal(canAccessPage('unknown', '/orders'), false)
})
test('account management follows the group hierarchy', () => {
  assert.deepEqual(assignableRoles('operator'), [])
  assert.deepEqual(assignableRoles('shop_admin'), ['operator'])
  assert.deepEqual(assignableRoles('admin'), ['operator', 'shop_admin'])
  assert.equal(canManageAccount('shop_admin', 'admin'), false)
  assert.equal(canManageAccount('shop_admin', 'shop_admin'), false)
  assert.equal(canManageAccount('shop_admin', 'operator'), true)
  assert.equal(canManageAccount('operator', 'operator'), false)
})
test('server field allowlist controls module switches and sensitive items independently', () => {
  const groups = [{ title: 'SalesDrive', toggle: 'salesdrive_enabled', items: [{ key: 'salesdrive_api_key' }] },
    { title: 'Backups', toggle: 'backup_enabled', items: [{ key: 'backup_hour' }] }]
  assert.deepEqual(filterSettingGroups(groups), [])
  const admin = filterSettingGroups(groups, ['salesdrive_enabled', 'backup_enabled'])
  assert.equal(admin.length, 2)
  assert.ok(admin.every((group) => group.toggle && group.items.length === 0))
  assert.equal(filterSettingGroups(groups, ['salesdrive_api_key'])[0].toggle, undefined)
  assert.equal(groups[0].items.length, 1, 'source definitions are not mutated')
})
