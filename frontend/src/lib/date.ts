const DATE_ONLY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const DISPLAY_DATE_LOCALE = 'en-US';
const DISPLAY_DATE_OPTIONS: Intl.DateTimeFormatOptions = {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
};
const DISPLAY_DATETIME_OPTIONS: Intl.DateTimeFormatOptions = {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
};

export const formatDisplayDate = (
  value: string | null | undefined,
  fallback = 'Date missing'
): string => {
  if (!value) {
    return fallback;
  }

  const date = DATE_ONLY_PATTERN.test(value)
    ? new Date(`${value}T00:00:00`)
    : new Date(value);

  if (Number.isNaN(date.getTime())) {
    return fallback;
  }

  return date.toLocaleDateString(DISPLAY_DATE_LOCALE, DISPLAY_DATE_OPTIONS);
};

export const formatDisplayDateTime = (
  value: string | null | undefined,
  fallback = 'Unknown'
): string => {
  if (!value) {
    return fallback;
  }

  const normalizedValue = DATE_ONLY_PATTERN.test(value)
    ? `${value}T00:00:00`
    : value;
  const date = new Date(normalizedValue);
  if (Number.isNaN(date.getTime())) {
    return fallback;
  }

  return date.toLocaleString(DISPLAY_DATE_LOCALE, DISPLAY_DATETIME_OPTIONS);
};
