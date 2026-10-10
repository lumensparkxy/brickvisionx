import { useState } from 'react';

export default function PreparedPages({sourceHash, pageCount, label}: {sourceHash: string; pageCount: number; label: string}) {
  const [index, setIndex] = useState(0);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const page = Math.min(Math.max(index, 0), pageCount - 1);
  const url = `/api/v1/sources/${sourceHash}/pages/${page}`;
  const go = (next: number) => { if (next !== page) { setStatus('loading'); setIndex(next); } };
  return <section className="prepared-pages" aria-label={`${label} official pages`}>
    <div className="prepared-page-frame">
      {status === 'loading' && <p role="status">Loading page…</p>}
      {status === 'error' && <p role="alert">This page could not be loaded. Prepare the booklet again to restore it.</p>}
      <img key={url} src={url} alt={`Official booklet page ${page + 1}`} hidden={status === 'error'}
        onLoad={() => setStatus('ready')} onError={() => setStatus('error')}/>
    </div>
    <div className="prepared-page-controls">
      <button className="secondary" disabled={page === 0} onClick={() => go(page - 1)}>Previous page</button>
      <span aria-live="polite">Page {page + 1} of {pageCount}</span>
      <button className="secondary" disabled={page === pageCount - 1} onClick={() => go(page + 1)}>Next page</button>
      <a href={url} target="_blank" rel="noreferrer">Open full-size page {page + 1} ↗</a>
    </div>
  </section>;
}
