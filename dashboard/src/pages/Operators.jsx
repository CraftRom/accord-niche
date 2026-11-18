import { useEffect, useId, useRef, useState } from 'react'

import { api, getSession } from '../api'
import { ROLE_TITLES, assignableRoles, canManageAccount } from '../roles'
import { Empty, ErrorBar, Field, Loading, Modal, confirmPurge, useToast } from '../components/ui'
import { PageHeader, SectionCard } from '../components/page'

// Значення мають збігатися з OperatorRole на бекенді. «admin» історично
// означає системного адміністратора з .env — його в панелі не створюють,
// тому в списку вибору його немає, а в таблиці підпис потрібен.
const ROLE_LABEL = ROLE_TITLES

// Ролі, які можна призначити з панелі.
const CREATABLE_ROLES = [
  { value: 'operator', label: 'Менеджер',
    hint: 'Працює із замовленнями й клієнтами' },
  { value: 'shop_admin', label: 'Адміністратор',
    hint: 'Керує модулями, налаштуваннями магазину та менеджерами' },
]

// Що відкриває кожна група — одна модель і для таблиці, і для попередження
// про зміну ролі (UI-022). Права перевіряє сервер; тут лише пояснення.
const ROLE_ACCESS = {
  admin: ['Замовлення, клієнти й чати', 'Налаштування магазину й модулі', 'Облікові записи менеджерів', 'Інфраструктура, журнали й резервні копії'],
  shop_admin: ['Замовлення, клієнти й чати', 'Налаштування магазину й модулі', 'Облікові записи менеджерів'],
  operator: ['Замовлення, клієнти й чати'],
}
export function roleChange(from, to) {
  const before = ROLE_ACCESS[from] || [], after = ROLE_ACCESS[to] || []
  return { lost: before.filter((item) => !after.includes(item)), gained: after.filter((item) => !before.includes(item)) }
}

const availableRoles = () => CREATABLE_ROLES.filter((role) => assignableRoles(getSession().role).includes(role.value))

const MIN_PASSWORD_LENGTH = 12
const MAX_PASSWORD_LENGTH = 128
const characterCount = (value) => [...value].length

function formatDate(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString('uk-UA', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function OperatorForm({ operator, onClose, onSaved }) {
  const notify = useToast()
  const editing = Boolean(operator?.id)
  const [form, setForm] = useState({
    login: operator?.login || '',
    name: operator?.name || '',
    password: '',
    role: operator?.role || 'operator',
  })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [touched, setTouched] = useState({})
  const saving = useRef(false)
  const formId = useId()

  const loginValid = editing || /^[A-Za-z0-9_.-]{3,64}$/.test(form.login.trim())
  const passwordLength = characterCount(form.password)
  const passwordValid = (editing && form.password === '') ||
    (passwordLength >= MIN_PASSWORD_LENGTH && passwordLength <= MAX_PASSWORD_LENGTH)
  const nameProblem = characterCount(form.name.trim()) > 128
    ? 'Ім’я має містити не більше 128 символів.'
    : form.name.includes('\0') ? 'Приберіть неприпустимий символ з імені.' : ''
  const nameValid = !nameProblem
  const canSave = loginValid && passwordValid && nameValid
  const touch = (field) => () => setTouched((old) => ({ ...old, [field]: true }))
  const close = () => { if (!saving.current) onClose() }

  const set = (key) => (e) => {
    setForm((f) => ({ ...f, [key]: e.target.value }))
    setError('')
  }

  const save = async () => {
    if (saving.current || !canSave) return
    saving.current = true
    setBusy(true)
    setError('')
    try {
      if (editing) {
        const payload = { name: form.name.trim() }
        if (form.role !== operator.role) {
          const { lost } = roleChange(operator.role, form.role)
          if (lost.length && !window.confirm(`${operator.name || operator.login} втратить доступ: ${lost.join(', ')}. Змінити групу?`)) return
          payload.role = form.role
        }
        // Порожнє поле означає «пароль не змінюємо»
        if (form.password) payload.password = form.password
        await api.operators.update(operator.id, payload)
        notify('Дані оновлено')
      } else {
        await api.operators.create({
          login: form.login.trim(),
          name: form.name.trim(),
          password: form.password,
          role: form.role,
        })
        notify('Обліковий запис створено')
      }
      onSaved()
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      saving.current = false
      setBusy(false)
    }
  }

  return (
    <Modal
      title={editing ? `Обліковий запис «${operator.login}»` : 'Новий обліковий запис'}
      onClose={close}
      footer={
        <>
          <button className="btn ghost" onClick={close} disabled={busy}>Скасувати</button>
          <button className="btn" onClick={save} disabled={!canSave || busy}>
            {busy ? 'Збереження…' : editing ? 'Зберегти' : 'Створити'}
          </button>
        </>
      }
    >
      <ErrorBar error={error} />

      {!editing && (
        <Field label="Логін" htmlFor={`${formId}-login`} hint={<span id={`${formId}-login-hint`}>
          {touched.login && !loginValid
            ? 'Введіть від 3 до 64 символів: латиниця, цифри, крапка, дефіс або підкреслення.'
            : 'Від 3 до 64 символів: латиниця, цифри, крапка, дефіс або підкреслення. Змінити пізніше не можна.'}
        </span>}>
          <input id={`${formId}-login`} className="input" value={form.login} onChange={set('login')}
            onBlur={touch('login')} aria-invalid={Boolean(touched.login && !loginValid)} aria-describedby={`${formId}-login-hint`} disabled={busy} autoFocus />
        </Field>
      )}

      <Field label="Імʼя" htmlFor={`${formId}-name`} hint={<span id={`${formId}-name-hint`}>
        {touched.name && nameProblem
          ? nameProblem
          : 'Показується в панелі. До 128 символів; можна залишити порожнім.'}
      </span>}>
        <input id={`${formId}-name`} className="input" value={form.name} onChange={set('name')} onBlur={touch('name')}
          aria-invalid={Boolean(touched.name && !nameValid)} aria-describedby={`${formId}-name-hint`} disabled={busy} />
      </Field>

      <Field
        label={editing ? 'Новий пароль' : 'Пароль'}
        htmlFor={`${formId}-password`}
        hint={<span id={`${formId}-password-hint`}>
          {touched.password && !passwordValid
            ? 'Мінімум 12 символів, максимум 128. Пробіли й спецсимволи дозволені.'
            : editing
              ? 'Лишіть порожнім, щоб не змінювати. Мінімум 12 символів, максимум 128.'
              : 'Мінімум 12 символів, максимум 128. Не лише цифри.'}
        </span>}
      >
        <input
          className="input"
          id={`${formId}-password`}
          type="password"
          value={form.password}
          onChange={set('password')}
          onBlur={touch('password')}
          aria-invalid={Boolean(touched.password && !passwordValid)}
          aria-describedby={`${formId}-password-hint`}
          disabled={busy}
          autoComplete="new-password"
        />
      </Field>

      <Field
        label="Системна група"
        htmlFor={`${formId}-role`}
        hint={
          (availableRoles().find((r) => r.value === form.role) || { hint: 'Системний доступ' }).hint +
          '. Секрети бота, системні розклади й відновлення копій лишаються за системним ' +
          'адміністратором — його обліковий запис задається у файлі .env.domains'
        }
      >
        <select id={`${formId}-role`} className="input" value={form.role} onChange={set('role')} disabled={busy}>
          {editing && operator.role === 'admin' && <option value="admin" disabled>Системний адміністратор</option>}
          {availableRoles().map((r) => (
            <option key={r.value} value={r.value}>{r.label}</option>
          ))}
        </select>
      </Field>
      {editing && form.role !== operator.role && (() => {
        const { lost, gained } = roleChange(operator.role, form.role)
        return (
          <div className={`card role-change-notice ${lost.length ? 'warn' : ''}`} role="status">
            <strong>Після збереження зміняться права</strong>
            {lost.length > 0 && <p>Втратить доступ: {lost.join(', ')}.</p>}
            {gained.length > 0 && <p>Отримає доступ: {gained.join(', ')}.</p>}
          </div>
        )
      })()}
    </Modal>
  )
}

export default function Operators() {
  const notify = useToast()
  const [rows, setRows] = useState(null)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(null)

  const load = () => {
    api.operators
      .list()
      .then(setRows)
      .catch((err) => setError(err.message))
  }

  useEffect(load, [])

  const toggle = async (operator) => {
    try {
      if (operator.is_active) {
        await api.operators.remove(operator.id)
        notify('Доступ вимкнено')
      } else {
        await api.operators.update(operator.id, { is_active: true })
        notify('Доступ повернено')
      }
      load()
    } catch (err) {
      notify(err.message, 'bad')
    }
  }

  const purge = async (operator) => {
    if (!confirmPurge(operator.login, 'Обліковий запис зникне назавжди.')) return
    try {
      await api.operators.purge(operator.id)
      notify('Обліковий запис стерто')
      load()
    } catch (err) {
      notify(err.message, 'bad')
    }
  }

  if (error && !rows) return <ErrorBar error={error} />
  if (!rows) return <Loading />

  return (
    <>
      <PageHeader
        help="operators"
        title="Команда та доступ"
        description="Хто має доступ до панелі й на якому рівні"
        actions={<>
          <button className="btn" onClick={() => setEditing({})}>Новий обліковий запис</button>
        </>}
      />

      <ErrorBar error={error} />

      <SectionCard title="Що може кожна група" description="Права перевіряє сервер; прихована кнопка не замінює перевірки доступу.">
        <div className="table-wrap" aria-label="Системні групи">
          <table><thead><tr><th>Системна група</th><th>Доступ</th></tr></thead><tbody>
            {['admin', 'shop_admin', 'operator'].map((role) => (
              <tr key={role}><td>{ROLE_LABEL[role]}</td><td>{ROLE_ACCESS[role].join(' · ')}{role === 'admin' ? '. Обліковий запис задається на сервері.' : ''}</td></tr>
            ))}
          </tbody></table>
        </div>
      </SectionCard>

      {rows.length === 0 ? (
        <Empty title="Менеджерів ще немає">
          Поки що в панель заходить лише адміністратор із налаштувань сервера.
        </Empty>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Логін</th>
                <th>Імʼя</th>
                <th>Системна група</th>
                <th>Останній вхід</th>
                <th>Статус</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((o) => (
                <tr key={o.id} style={{ opacity: o.is_active ? 1 : 0.55 }}>
                  <td>{o.login}</td>
                  <td>{o.name || '—'}</td>
                  <td>{ROLE_LABEL[o.role] || o.role}</td>
                  <td className="faint">{formatDate(o.last_login_at)}</td>
                  <td>
                    <span className={`chip ${o.is_active ? 'ok' : ''}`}>
                      {o.is_active ? 'Активний' : 'Вимкнений'}
                    </span>
                  </td>
                  <td>
                    <div className="row">
                      <button className="btn small ghost" disabled={!canManageAccount(getSession().role, o.role)} onClick={() => setEditing(o)}>
                        Змінити
                      </button>
                      <button
                        className={o.is_active ? 'btn danger small' : 'btn small ghost'}
                        disabled={!canManageAccount(getSession().role, o.role) || getSession().operator_id === o.id}
                        onClick={() => toggle(o)}
                        title="Доступ закривається, історія дій лишається"
                      >
                        {o.is_active ? 'Вимкнути' : 'Увімкнути'}
                      </button>
                      <button
                        className="btn danger small"
                        disabled={!canManageAccount(getSession().role, o.role) || getSession().operator_id === o.id}
                        onClick={() => purge(o)}
                        title="Стерти запис назавжди. Імʼя в замовленнях збережеться"
                      >
                        Стерти
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing && (
        <OperatorForm
          operator={editing.id ? editing : null}
          onClose={() => setEditing(null)}
          onSaved={load}
        />
      )}
    </>
  )
}
