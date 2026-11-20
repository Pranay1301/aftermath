import asyncio,functools,http.server,json,pathlib,threading
from playwright.async_api import async_playwright
R=pathlib.Path(__file__).resolve().parents[1]
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args): pass
async def main():
 server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(R)))
 threading.Thread(target=server.serve_forever,daemon=True).start()
 async with async_playwright()as p:
  b=await p.chromium.launch();pg=await b.new_page(viewport={'width':1280,'height':1000});errors=[];pg.on('pageerror',lambda e:errors.append(str(e)));await pg.goto('http://127.0.0.1:'+str(server.server_port)+'/web/eventual.html');await pg.wait_for_selector('.policy');data=json.loads((R/'evidence/eventual-matrix.json').read_text());seen=0
  for phase in ['before_visibility','after_visibility']:
   await pg.locator('#phase').select_option(phase)
   for cut in ['after_effect','during_effect','before_effect','after_intent','before_intent','after_receipt','none']:
    await pg.locator('#cut').select_option(cut);cards=pg.locator('.policy');assert await cards.count()==3
    for i,policy in enumerate(['blind','receipt','guarded']):
     r=next(x for x in data['results']if x['policy']==policy and x['cut']==cut)[phase];assert await cards.nth(i).locator('.score strong').inner_text()==str(r['effect_count']);expected='DUPLICATE SIDE EFFECT'if r['duplicate']else'HELD / NOT COMPLETED'if r['held']else'CONFIRMED / ONE EFFECT';assert await cards.nth(i).locator('.outcome').inner_text()==expected;seen+=1
  await pg.locator('#cut').select_option('after_effect');await pg.locator('summary').nth(2).click();assert await pg.locator('details').nth(2).get_attribute('open')is not None;await pg.locator('summary').nth(2).click()
  for w in [1280,390,320]:
   await pg.set_viewport_size({'width':w,'height':1000});await pg.evaluate('scrollTo(0,0)');await pg.screenshot(path=str(R/f'docs/eventual-{w}.png'),full_page=True);assert await pg.evaluate('document.documentElement.scrollWidth<=innerWidth')
  assert not errors;print(json.dumps({'viewsChecked':14,'cardsAgainstRawEvidence':seen,'widths':[1280,390,320],'pageErrors':errors,'status':'PASS'}));await b.close()
 server.shutdown()
asyncio.run(main())
