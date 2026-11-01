// Native Node test events, including parent assertions omitted by Node 22 JUnit.
// Raw diagnostics stay in ignored runner-local evidence; Python allowlists publication.
export default async function* (events) {
  const scalar = value => value === null || typeof value === 'boolean' ||
    (typeof value === 'number' && Number.isFinite(value));
  for await (const { type, data } of events) {
    if (type !== 'test:pass' && type !== 'test:fail') continue;
    const error = data.details?.error;
    const cause = error?.cause;
    const row = {
      event: type, name: data.name, file: data.file, kind: data.details?.type,
      duration_ms: data.details?.duration_ms, skipped: Boolean(data.skip || data.todo),
      failure_type: error?.failureType,
      error: error ? `${String(error)}\n${String(cause)}` : '',
    };
    if (cause && scalar(cause.actual) && scalar(cause.expected)) {
      row.actual = cause.actual;
      row.expected = cause.expected;
    }
    yield JSON.stringify(row) + '\n';
  }
}
