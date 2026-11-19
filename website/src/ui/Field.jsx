export function Field({name, label, value, onChange, required=true, type='text', placeholder='', autoComplete, maxLength,error,inputProps={}}) {
  const id='accord-'+name
  return <label className="shop-field" htmlFor={id}><span>{label}{required ? ' *' : ''}</span><input id={id} name={name} type={type} value={value} required={required} {...inputProps}
    aria-invalid={error?true:undefined} aria-describedby={error?id+'-error':undefined}
    maxLength={maxLength} placeholder={placeholder} autoComplete={autoComplete} onChange={e=>onChange(e.target.value)} />
    {error && <small className="field-error" id={id+'-error'}>{error}</small>}</label>
}
