import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { getConfig, setConfig, type AppConfig, type ConfigUpdate } from '@/services/configApi';

export const CONFIG_KEY = ['config'] as const;

/**
 * The AI toggles, owned by the server so they survive a reload and apply to
 * the scheduler as well as this tab.
 *
 * The PUT returns the whole resulting config, so the response is written
 * straight into the cache rather than invalidating and asking again — the
 * server already told us the answer.
 *
 * `config` is undefined until the first load. Callers render the toggles from
 * it rather than from a local mirror, so a failed write snaps the switch back
 * to what the server actually holds instead of lying about it.
 */
export const useAppConfig = () => {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: CONFIG_KEY,
    queryFn: getConfig,
    // Only ever changes because someone in this app changed it, and that path
    // writes the cache itself.
    staleTime: Infinity,
  });

  const mutation = useMutation({
    mutationFn: (update: ConfigUpdate) => setConfig(update),
    onSuccess: (config: AppConfig) => queryClient.setQueryData(CONFIG_KEY, config),
  });

  return {
    config: query.data,
    loading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
    saving: mutation.isPending,
    update: (patch: ConfigUpdate) => mutation.mutateAsync(patch),
  };
};
