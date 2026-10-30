/** Large native markers need to stay inside the reader's content box. */
export const wideList = (start = 1, count = 1) => Math.max(Math.abs(start), Math.abs(start + count - 1)) >= 100
