import { useEffect, useRef } from "react";
import { buildStreamUrl, DEFAULT_CAMERA_HARDWARE_ID } from "../api/camera";
import { Card, SectionTitle } from "../components/common";

export function CameraPage() {
  const imgRef = useRef<HTMLImageElement>(null);

  // Belt-and-braces: unmounting the <img> should abort the stream, but Chrome
  // has historically been sloppy about tearing down MJPEG connections, and a
  // stuck stream holds the sensor on. The agent's lease TTL would reap it
  // anyway; this just makes teardown immediate.
  //
  // The check must be deferred: cleanup also runs during StrictMode's
  // simulated unmount, where the node stays in the document and React would
  // never re-assign the unchanged src we cleared. Only a real unmount
  // actually detaches the node.
  useEffect(() => {
    const img = imgRef.current;
    return () => {
      setTimeout(() => {
        if (img && !img.isConnected) {
          img.src = "";
        }
      }, 0);
    };
  }, []);

  return (
    <div className="space-y-6">
      <SectionTitle
        subtitle="Live view from the Pi Camera Module"
        title="Camera"
      />
      <Card>
        {/* src is set declaratively in JSX on purpose: StrictMode double-invokes
            effects but does not re-create committed DOM nodes, so this issues
            exactly one stream connection. Do not move it into an effect. */}
        <img
          alt="Live camera stream"
          className="mx-auto w-full max-w-3xl rounded-lg border border-slate-200 bg-slate-900"
          ref={imgRef}
          src={buildStreamUrl(DEFAULT_CAMERA_HARDWARE_ID)}
        />
      </Card>
    </div>
  );
}
