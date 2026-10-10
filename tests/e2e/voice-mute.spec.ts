import {test,expect} from '@playwright/test';
// Offline: Gradium WebSockets, the token route and the reply route are faked. Chromium's fake
// microphone provides non-silent audio, so "loud" chunks show whether real mic audio is sent.
test.use({permissions:['microphone'],launchOptions:{args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream','--autoplay-policy=no-user-gesture-required']}});

test('muting the microphone keeps the reply thinking and speaking',async({page})=>{
  const audio={loud:0,silent:0};const spoken:string[]=[];let release=()=>{};
  await page.route('**/api/v1/voice/token',r=>r.fulfill({json:{token:'synthetic',expires_at:'2026-10-10T12:00:00Z'}}));
  await page.route('**/api/v1/voice/reply',async r=>{
    await new Promise<void>(resolve=>{release=resolve;});
    await r.fulfill({json:{text:'Here is my answer.',action:{type:'none'}}});
  });
  await page.routeWebSocket(/api\.gradium\.ai\/api\/speech\/asr/,ws=>ws.onMessage(raw=>{
    const message=JSON.parse(String(raw));
    if(message.type==='setup')ws.send(JSON.stringify({type:'ready'}));
    if(message.type==='audio'){const pcm=new Int16Array(new Uint8Array(Buffer.from(message.audio,'base64')).buffer);
      if(pcm.some(value=>Math.abs(value)>8))audio.loud++;else audio.silent++;}
  }));
  await page.routeWebSocket(/api\.gradium\.ai\/api\/speech\/tts/,ws=>ws.onMessage(raw=>{
    const message=JSON.parse(String(raw));
    if(message.type==='text'){spoken.push(message.text);
      ws.send(JSON.stringify({type:'audio',audio:Buffer.from(new Int16Array(4800).buffer).toString('base64')}));
      ws.send(JSON.stringify({type:'end_of_stream'}));}
  }));
  await page.goto('/');
  const status=page.locator('.voice-hero .voice-copy [role=status]');
  await page.getByRole('button',{name:'Start voice chat'}).click();
  await expect(status).toContainText('Listening');
  await expect.poll(()=>audio.loud,{timeout:10_000}).toBeGreaterThan(0);

  const input=page.locator('#voice-command-hero');
  await input.fill('What should I build first?');await input.press('Enter');
  await expect(status).toContainText('Thinking');
  await page.getByRole('button',{name:'Mute microphone'}).click();
  await expect(page.getByRole('button',{name:'Unmute microphone'})).toHaveAttribute('aria-pressed','true');
  await expect(status).toContainText('Microphone muted · thinking');
  release();
  await expect(page.locator('.voice-hero .voice-transcript li.assistant')).toContainText('Here is my answer.');
  await expect.poll(()=>spoken).toEqual(['Here is my answer.']);
  await expect(status).toContainText('Microphone muted — type a command');
  await expect(page.getByRole('button',{name:'Stop voice chat'})).toBeVisible();

  const loudWhileMuted=audio.loud;const silentWhileMuted=audio.silent;
  await page.waitForTimeout(1500);
  expect(audio.loud).toBe(loudWhileMuted);
  expect(audio.silent).toBeGreaterThan(silentWhileMuted);

  await page.getByRole('button',{name:'Unmute microphone'}).click();
  await expect(status).toContainText('Listening');
  await expect.poll(()=>audio.loud,{timeout:10_000}).toBeGreaterThan(loudWhileMuted);
  await page.getByRole('button',{name:'Stop voice chat'}).click();
  await expect(page.getByRole('button',{name:'Mute microphone'})).toHaveCount(0);
});
