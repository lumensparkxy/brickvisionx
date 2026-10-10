/** Refresh cached CORS response headers after adding the second production alias.
 * The stable query changes the cache key, never the published bytes or their hashes.
 */
export function modelAssetUrl(value: string | URL): URL {
  const url = new URL(value, location.origin);
  if (url.origin === 'https://storage.googleapis.com') url.searchParams.set('g2b-transport', '2');
  return url;
}
