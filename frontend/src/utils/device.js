/**
 * Turn a raw User-Agent string into a short "Browser on OS" label for the sessions list.
 * Deliberately simple: we only need something a person recognises, not full UA parsing.
 */
export function describeUserAgent(ua) {
  if (!ua) return { label: 'Unknown device', mobile: false }
  const browser =
    (/Edg\//.test(ua) && 'Edge') ||
    (/OPR\/|Opera/.test(ua) && 'Opera') ||
    (/Firefox\//.test(ua) && 'Firefox') ||
    (/Chrome\//.test(ua) && 'Chrome') ||
    (/Safari\//.test(ua) && 'Safari') ||
    (/python|httpx|curl|PostmanRuntime/i.test(ua) && 'API client') ||
    null
  const os =
    (/Android/.test(ua) && 'Android') ||
    (/iPhone|iPad|iOS/.test(ua) && 'iOS') ||
    (/Windows/.test(ua) && 'Windows') ||
    (/Mac OS X|Macintosh/.test(ua) && 'macOS') ||
    (/Linux/.test(ua) && 'Linux') ||
    null
  const mobile = /Mobile|Android|iPhone|iPad/.test(ua)
  if (browser && os) return { label: `${browser} on ${os}`, mobile }
  return { label: browser || os || ua.slice(0, 40), mobile }
}
