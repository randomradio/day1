import { useEffect, useState } from 'react';
import { checkHealth } from '../api/client';

export default function ConnectionBadge() {
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const check = () => checkHealth().then(setConnected);
    check();
    const id = setInterval(check, 10_000);
    return () => clearInterval(id);
  }, []);

  return (
    <span className="flex items-center gap-1.5 text-sm">
      <span
        className={`inline-block h-2.5 w-2.5 rounded-full ${
          connected ? 'bg-green-500' : 'bg-red-500'
        }`}
      />
      {connected ? 'Connected' : 'Disconnected'}
    </span>
  );
}
