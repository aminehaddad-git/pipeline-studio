/**
 * Downloads a file from a protected endpoint.
 * The token cannot travel in a plain link, so we fetch with the header,
 * receive the file as a blob, and trigger the download from memory.
 */
export async function downloadFile(url, token, fallbackName = 'export') {
  const res = await fetch(`http://localhost:8000${url}`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!res.ok) {
    let msg = 'Export failed';
    try {
      const data = await res.json();
      if (typeof data.detail === 'string') msg = data.detail;
    } catch { /* not JSON, keep default */ }
    throw new Error(msg);
  }

  // Recover the filename proposed by the server
  let filename = fallbackName;
  const disp = res.headers.get('Content-Disposition');
  if (disp) {
    const match = disp.match(/filename="?([^"]+)"?/);
    if (match) filename = match[1];
  }

  const blob = await res.blob();
  const objectUrl = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(objectUrl);
}