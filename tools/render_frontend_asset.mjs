/** Read one already root-confined built asset before sending any successful response. */
import {readFile,stat} from 'node:fs/promises';

export class FrontendAssetReadError extends Error {
  constructor(assetPath,expectedBytes,actualBytes){
    super(`Incomplete built frontend asset read: ${assetPath} (expected ${expectedBytes} bytes, received ${actualBytes})`);
    this.name='FrontendAssetReadError';
    this.diagnostic={code:'frontend_asset_incomplete_read',asset_path:assetPath,expected_bytes:expectedBytes,actual_bytes:actualBytes};
  }
}

export async function readFrontendAsset(file,assetPath,{read=readFile}={}){
  const info=await stat(file);
  if(!info.isFile()||info.size>16_000_000)throw new Error('Asset size or regular-file bound');
  const bytes=await read(file);
  if(bytes.length===0||bytes.length!==info.size)throw new FrontendAssetReadError(assetPath,info.size,bytes.length);
  return bytes;
}

export async function serveFrontendAsset(res,file,assetPath,contentType,onReadFailure,io){
  let bytes;
  try{bytes=await readFrontendAsset(file,assetPath,io);}
  catch(error){
    if(!(error instanceof FrontendAssetReadError))throw error;
    res.writeHead(503,{'Content-Type':'text/plain'}).end('Built frontend asset read incomplete');
    onReadFailure(error);
    return false;
  }
  res.setHeader('Content-Type',contentType);
  res.end(bytes);
  return true;
}
