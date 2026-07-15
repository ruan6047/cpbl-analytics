export class ApiError extends Error {
  readonly path: string;
  readonly status: number;

  constructor(path: string, status: number) {
    super(`API ${path} → ${status}`);
    this.name = "ApiError";
    this.path = path;
    this.status = status;
  }
}

export async function optionalNotFound<T>(promise: Promise<T>): Promise<T | null> {
  try {
    return await promise;
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}
