import {useEffect,useRef} from 'react'
import {mountDialog} from './dialog'

export function useDialog(element,open,onClose) {
  const close=useRef(onClose);close.current=onClose
  useEffect(()=>{
    if(open)return mountDialog(element.current,()=>close.current())
  },[element,open])
}
