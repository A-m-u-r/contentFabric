// Configuration for API endpoints.
// In production VITE_API_URL can point at the deployed backend.
// In local browser dev we avoid depending on the current Vite proxy port for media.

export const API_BASE_URL = import.meta.env.VITE_API_URL || '';
export const LOCAL_BACKEND_ORIGIN = import.meta.env.VITE_LOCAL_API_URL || 'http://127.0.0.1:8000';

const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '::1']);
const BACKEND_PREFIXES = ['/api', '/videos', '/thumbnails', '/gallery', '/video'];

const isLocalBrowser = () => (
    typeof window !== 'undefined' && LOCAL_HOSTS.has(window.location.hostname)
);

const isLocalApiBase = () => {
    if (!API_BASE_URL) return true;
    try {
        return LOCAL_HOSTS.has(new URL(API_BASE_URL).hostname);
    } catch {
        return false;
    }
};

const shouldUseLocalBackend = (path) => (
    isLocalApiBase()
    && isLocalBrowser()
    && BACKEND_PREFIXES.some((prefix) => path === prefix || path.startsWith(`${prefix}/`))
);

export const getApiUrl = (path) => {
    if (!path) return '';
    if (path.startsWith('blob:') || path.startsWith('data:')) return path;
    if (path.startsWith('http')) {
        try {
            const parsed = new URL(path);
            if (
                isLocalApiBase()
                && isLocalBrowser()
                && LOCAL_HOSTS.has(parsed.hostname)
                && BACKEND_PREFIXES.some((prefix) => parsed.pathname === prefix || parsed.pathname.startsWith(`${prefix}/`))
            ) {
                return `${LOCAL_BACKEND_ORIGIN}${parsed.pathname}${parsed.search}${parsed.hash}`;
            }
        } catch {
            return path;
        }
        return path;
    }
    const normalizedPath = path.startsWith('/') ? path : `/${path}`;
    if (shouldUseLocalBackend(normalizedPath)) return `${LOCAL_BACKEND_ORIGIN}${normalizedPath}`;
    return `${API_BASE_URL}${normalizedPath}`;
};
