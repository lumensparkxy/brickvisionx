export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}
export async function request<T>(path: string): Promise<T> {
  const response = await fetch(`/api/v1${path}`);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, body?.detail?.code ?? 'request_failed',
      body?.detail?.message ?? 'The request could not be completed.');
  }
  return response.json() as Promise<T>;
}
