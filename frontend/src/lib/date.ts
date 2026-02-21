const DATE_ONLY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

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

  return date.toLocaleDateString();
};

export const formatDisplayDateTime = (
  value: string | null | undefined,
  fallback = 'Unknown'
): string => {
  if (!value) {
    return fallback;
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return fallback;
  }

  return date.toLocaleString();
};
