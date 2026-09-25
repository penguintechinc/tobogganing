import { useAuth } from '../context/AuthContext';

export function useRole() {
  const { user } = useAuth();
  const role = user?.role || 'viewer';

  const canWrite = () => role !== 'viewer';

  return { role, canWrite };
}
