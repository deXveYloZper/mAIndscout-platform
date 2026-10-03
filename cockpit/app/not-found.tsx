import Link from "next/link";

export default function NotFound() {
  return (
    <div className="panel">
      <h1>Not found</h1>
      <p className="sub">This person or job does not exist here. It may have been erased.</p>
      <p><Link href="/">Back to jobs</Link></p>
    </div>
  );
}
