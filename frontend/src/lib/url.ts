const ALLOWED_EXTERNAL_PROTOCOLS = new Set(['http:', 'https:']);

export const getSafeExternalUrl = (value: string | null | undefined): string | null => {
  if (!value) {
    return null;
  }

  try {
    const parsedUrl = new URL(value);
    return ALLOWED_EXTERNAL_PROTOCOLS.has(parsedUrl.protocol.toLowerCase())
      ? parsedUrl.toString()
      : null;
  } catch {
    return null;
  }
};
