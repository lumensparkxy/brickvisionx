import assert from 'node:assert/strict';
import {mkdtemp,readFile,writeFile,rm} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import test from 'node:test';
import {FrontendAssetReadError,serveFrontendAsset} from '../tools/render_frontend_asset.mjs';

function response(){return {statusCode:200,headers:{},bodies:[],
  setHeader(name,value){this.headers[name]=value;},
  writeHead(code,headers){this.statusCode=code;Object.assign(this.headers,headers);return this;},
  end(bytes){this.bodies.push(bytes);return this;}};}

test('complete built script bytes keep the successful response unchanged',async t=>{
  const dir=await mkdtemp(join(tmpdir(),'guide2build-render-asset-normal-'));
  t.after(()=>rm(dir,{recursive:true,force:true}));
  const file=join(dir,'chunk.js'),bytes=Buffer.from('export const ready=true;\n');
  await writeFile(file,bytes);
  const res=response(),failures=[];
  assert.equal(await serveFrontendAsset(res,file,'/assets/chunk.js','text/javascript',error=>failures.push(error)),true);
  assert.equal(res.statusCode,200);
  assert.equal(res.headers['Content-Type'],'text/javascript');
  assert.deepEqual(res.bodies,[bytes]);
  assert.deepEqual(failures,[]);
  assert.deepEqual(await readFile(file),bytes);
});

test('zero and short reads never send a successful script and retain exact size diagnostics',async t=>{
  const dir=await mkdtemp(join(tmpdir(),'guide2build-render-asset-incomplete-'));
  t.after(()=>rm(dir,{recursive:true,force:true}));
  const file=join(dir,'chunk.js'),bytes=Buffer.from('export const ready=true;\n');
  await writeFile(file,bytes);
  for(const actual of [Buffer.alloc(0),bytes.subarray(0,bytes.length-1)]){
    const res=response(),failures=[];
    const result=await serveFrontendAsset(res,file,'/assets/chunk.js','text/javascript',error=>failures.push(error),{read:async requested=>{
      assert.equal(requested,file);return actual;
    }});
    assert.equal(result,false);
    assert.equal(res.statusCode,503);
    assert.equal(res.headers['Content-Type'],'text/plain');
    assert.deepEqual(res.bodies,['Built frontend asset read incomplete']);
    assert.equal(failures.length,1);
    assert.ok(failures[0] instanceof FrontendAssetReadError);
    assert.deepEqual(failures[0].diagnostic,{code:'frontend_asset_incomplete_read',asset_path:'/assets/chunk.js',
      expected_bytes:bytes.length,actual_bytes:actual.length});
    assert.match(failures[0].message,new RegExp(`expected ${bytes.length} bytes, received ${actual.length}`));
  }
  assert.deepEqual(await readFile(file),bytes);
});
