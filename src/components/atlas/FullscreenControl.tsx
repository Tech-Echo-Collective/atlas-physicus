import { useEffect, useState, type RefObject } from 'react';

interface FullscreenControlProps {
  targetRef: RefObject<HTMLElement | null>;
}

export function FullscreenControl({ targetRef }: FullscreenControlProps) {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const isSupported =
    typeof document !== 'undefined' && document.fullscreenEnabled;

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(document.fullscreenElement === targetRef.current);
    };

    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () =>
      document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, [targetRef]);

  const toggleFullscreen = async () => {
    if (!isSupported || !targetRef.current) {
      return;
    }

    if (document.fullscreenElement) {
      await document.exitFullscreen();
    } else {
      await targetRef.current.requestFullscreen();
    }
  };

  return (
    <button
      className="fullscreen-control"
      type="button"
      onClick={() => void toggleFullscreen()}
      disabled={!isSupported}
      aria-label={isFullscreen ? 'Exit fullscreen atlas' : 'Enter fullscreen atlas'}
      title={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
    >
      <span aria-hidden="true">{isFullscreen ? '↙' : '↗'}</span>
      {isFullscreen ? 'Exit' : 'Fullscreen'}
    </button>
  );
}
