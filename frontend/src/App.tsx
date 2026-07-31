import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import Home from './pages/Home';

/**
 * One screen, one provider.
 *
 * No router: there is a single view, and react-router was shipping a matcher
 * and a history stack to decide between "/" and a 404 page. No theme provider
 * either — FT is one palette on paper, and a dark mode nobody asked for is a
 * class toggle plus a second set of tokens to keep in sync.
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // The API is local, so a failed request means the backend is down;
      // retrying once surfaces that quickly instead of hanging.
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

const App = () => (
  <QueryClientProvider client={queryClient}>
    <Home />
  </QueryClientProvider>
);

export default App;
