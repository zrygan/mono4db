export type SiteId = 'site1' | 'site2' | 'site3';
export type SiteRole = 'central' | 'leaf';
export type FragmentId = 'A' | 'B';

export interface SiteInfo {
  readonly id: SiteId;
  readonly role: SiteRole;
  readonly url: string;                 // base URL of the site's web app
  readonly fragment: FragmentId | null; // null = central (holds all rows)
}

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Missing environment variable: ${name}`);
  return value;
}

export const SITES: Readonly<Record<SiteId, SiteInfo>> = Object.freeze({
  site1: { id: 'site1', role: 'central', url: requireEnv('CENTRAL_SITE_URL'), fragment: null },
  site2: { id: 'site2', role: 'leaf',    url: requireEnv('LEAF1_SITE_URL'),   fragment: 'A' },
  site3: { id: 'site3', role: 'leaf',    url: requireEnv('LEAF2_SITE_URL'),   fragment: 'B' },
});

function isSiteId(value: string | undefined): value is SiteId {
  return value !== undefined && value in SITES;
}

const siteId = process.env.SITE_ID;
if (!isSiteId(siteId)) throw new Error(`Invalid SITE_ID: ${siteId}`);

export const SELF_ID: SiteId = siteId;
export const self: SiteInfo = SITES[SELF_ID];
export const central: SiteInfo = SITES.site1;
export const peers: readonly SiteInfo[] = Object.values(SITES).filter(s => s.id !== SELF_ID);

export function leafFor(fragment: FragmentId): SiteInfo {
  const leaf = Object.values(SITES).find(s => s.fragment === fragment);
  if (!leaf) throw new Error(`No leaf holds fragment ${fragment}`);
  return leaf;
}
