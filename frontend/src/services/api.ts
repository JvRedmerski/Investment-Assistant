const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

export interface HealthResponse {
  status: string;
  app_name: string;
  environment: string;
  version: string;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_URL}/health`);
  if (!response.ok) {
    throw new Error('Falha ao conectar com o backend');
  }
  return response.json();
}
