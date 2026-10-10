import IconArrowRight from '@tabler/icons-react/dist/esm/icons/IconArrowRight.mjs';
import type { FormEvent, ReactNode } from 'react';
import catalogue from '../../../../config/sets.json';
import './landing.css';

const setOptions = catalogue.sets.map(({set_number,name}) => ({set_number,name}));

export default function LandingPage({setNumber,onSetNumber,onFind,onTry,busy,children,publicMode=false,previewMode=false}: {
  setNumber:string; onSetNumber:(value:string)=>void; onFind:(event:FormEvent)=>void;
  onTry:()=>void; busy:boolean; publicMode?:boolean; previewMode?:boolean; children:ReactNode;
}) {
  return <>
    <header className="landing-header"><a href="/" className="brand">Guide2Build <span>3D</span></a><a className="how-link" href="#how-it-works">How it works</a></header>
    <main className="landing-main">
      <section className="landing-hero" aria-labelledby="landing-title">
        <div className="hero-copy">
          <span className="eyebrow">FROM BOOKLET TO BUILD</span>
          <h1 id="landing-title"><span>Small bricks.</span><span>A clearer picture.</span></h1>
          <p className="hero-intro">Follow the official booklet with a 3D view, one step at a time.</p>
          <form className="landing-search" onSubmit={onFind} noValidate>
            <label htmlFor="set-number">Your set number</label>
            <div className="landing-search-row"><select id="set-number" value={setNumber} onChange={event=>onSetNumber(event.target.value)} disabled={busy} aria-describedby="supported">{setOptions.map(({set_number,name})=><option key={set_number} value={set_number}>{set_number} - {name}</option>)}</select><button id="find-set" disabled={busy}>{busy?'Please wait…':'Find my set'}</button></div>
            <p id="supported">{previewMode?`${setOptions.length} set choices · Alpha models are unverified.`:publicMode?'Choose a set to see its available booklets.':`Official booklets for ${setOptions.length} sets · 3D candidate: 30669, alternate 02`}</p>
          </form>
          <button className="try-tutorial" disabled={busy} onClick={onTry}>{publicMode?'Find the plane set':'Try the plane tutorial'} <IconArrowRight size={22} aria-hidden="true"/></button>
          {busy&&<p className="landing-busy" role="status">Working on your request…</p>}
        </div>
        <figure className="hero-art"><figcaption>30669 / Alternate aeroplane<small>Illustrative preview</small></figcaption><img src="/images/landing/hero-plane.webp" width="1322" height="1190" alt="Illustration of a red and white brick plane on a yellow baseplate, surrounded by colourful bricks" fetchPriority="high"/></figure>
      </section>
      {children}
      <section className="how-it-works" id="how-it-works" tabIndex={-1} aria-labelledby="how-title">
        <span className="eyebrow">A SIMPLE WAY TO BUILD</span><h2 id="how-title">Three steps to a great build.</h2>
        <ol className="build-steps">
          <li><img src="/images/landing/step-brick.webp" width="640" height="420" alt="" loading="lazy"/><div className="build-step-copy"><span className="step-number" aria-hidden="true">01</span><div><h3>Find your set</h3><p>Choose your set from the list to get started.</p></div></div></li>
          <li><img src="/images/landing/step-booklet.webp" width="640" height="420" alt="" loading="lazy"/><div className="build-step-copy"><span className="step-number" aria-hidden="true">02</span><div><h3>Choose the booklet</h3><p>Select the official booklet. We’ll show the available version for your set.</p></div></div></li>
          <li><img src="/images/landing/step-tutorial.webp" width="640" height="420" alt="" loading="lazy"/><div className="build-step-copy"><span className="step-number" aria-hidden="true">03</span><div><h3>Build in 3D</h3><p>{previewMode?'Explore an alpha sample alongside its official booklet. Colours and placements are unverified.':publicMode?'Explore an available tutorial or unverified alpha model with your official booklet.':'Open an available 3D candidate alongside its guide. Other booklets can be prepared for reconstruction.'}</p></div></div></li>
        </ol>
      </section>
    </main>
    <footer className="landing-footer"><p>{publicMode?'Independent building companion.':'Independent prototype · PDF-assisted candidates are labelled for review.'}<br/>Not affiliated with or endorsed by the LEGO Group.</p><p className="artwork-note">Artwork is illustrative. Source and review details are available in the tutorial.</p></footer>
  </>;
}
