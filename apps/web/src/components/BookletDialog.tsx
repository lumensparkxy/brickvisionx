import { useEffect, useRef, type ReactNode } from 'react';
import IconX from '@tabler/icons-react/dist/esm/icons/IconX.mjs';

export default function BookletDialog({children,onClose}:{children:ReactNode;onClose:()=>void}) {
  const ref=useRef<HTMLDialogElement>(null);
  useEffect(()=>{
    const dialog=ref.current!;
    const previousOverflow=document.body.style.overflow;
    dialog.showModal();
    dialog.querySelector<HTMLElement>('#booklet-title')?.focus();
    document.body.style.overflow='hidden';
    return()=>{dialog.close();document.body.style.overflow=previousOverflow;document.getElementById('find-set')?.focus();};
  },[]);
  return <dialog ref={ref} className="booklet-dialog" aria-labelledby="booklet-title" onCancel={event=>{event.preventDefault();onClose();}} onKeyDown={event=>{
    if(event.key!=='Tab')return;
    const controls=[...event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]')].filter(el=>el.getClientRects().length>0);
    const first=controls[0],last=controls.at(-1);
    if(event.shiftKey&&(document.activeElement===first||document.activeElement?.id==='booklet-title')){event.preventDefault();last?.focus();}
    else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
  }}>
    <div className="booklet-toolbar"><button className="icon-button booklet-close" aria-label="Close booklet selection" onClick={onClose}><IconX size={22}/></button></div>
    {children}
  </dialog>;
}
