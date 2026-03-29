import { flattenErrors } from "./errors";

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderPrintWindowMarkup({ title, bodyContent, accentColor = "#1d4ed8" }) {
  return `<!DOCTYPE html>
<html lang="ar" dir="rtl">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>${escapeHtml(title)}</title>
    <style>
      :root {
        color-scheme: light;
        font-family: "Segoe UI", Tahoma, Arial, sans-serif;
      }

      body {
        margin: 0;
        background: #f3f6fb;
        color: #102a43;
      }

      .print-shell {
        min-height: 100vh;
        display: grid;
        grid-template-rows: auto 1fr;
      }

      .print-header {
        padding: 1rem 1.25rem;
        background: #ffffff;
        border-bottom: 1px solid #d8e1ef;
        box-shadow: 0 4px 14px rgba(12, 34, 64, 0.08);
      }

      .print-header h1 {
        margin: 0 0 0.35rem;
        font-size: 1.05rem;
        color: #12345a;
      }

      .print-header p {
        margin: 0;
        color: #52667a;
        line-height: 1.7;
      }

      .print-main {
        padding: 1rem;
      }

      .print-card {
        height: calc(100vh - 7.5rem);
        min-height: 620px;
        background: #ffffff;
        border: 1px solid #d8e1ef;
        border-radius: 14px;
        overflow: hidden;
        box-shadow: 0 10px 24px rgba(12, 34, 64, 0.08);
      }

      .print-status {
        display: flex;
        gap: 0.75rem;
        align-items: center;
        padding: 0.95rem 1.1rem;
        background: #f8fbff;
        border-bottom: 1px solid #d8e1ef;
      }

      .print-status strong {
        color: ${accentColor};
      }

      .print-actions {
        margin-inline-start: auto;
        display: flex;
        gap: 0.75rem;
        flex-wrap: wrap;
      }

      .print-button {
        border: 1px solid #c7d1e0;
        border-radius: 10px;
        padding: 0.6rem 0.9rem;
        background: #ffffff;
        color: #12345a;
        cursor: pointer;
        font: inherit;
      }

      .print-button--primary {
        border-color: ${accentColor};
        background: ${accentColor};
        color: #ffffff;
      }

      .print-frame {
        width: 100%;
        height: calc(100% - 68px);
        border: 0;
        background: #ffffff;
      }

      .loading-card,
      .error-card {
        width: min(640px, calc(100vw - 2rem));
        margin: 12vh auto 0;
        background: #ffffff;
        border: 1px solid #d8e1ef;
        border-radius: 14px;
        padding: 1.25rem;
        box-shadow: 0 10px 24px rgba(12, 34, 64, 0.08);
      }

      .error-card {
        border-color: #f2c6c2;
        background: #fff8f7;
      }

      @media print {
        .print-header,
        .print-status {
          display: none;
        }

        .print-main {
          padding: 0;
        }

        .print-card {
          height: auto;
          min-height: 0;
          border: 0;
          border-radius: 0;
          box-shadow: none;
        }

        .print-frame {
          height: 100vh;
        }
      }
    </style>
  </head>
  <body>
    ${bodyContent}
  </body>
</html>`;
}

function writePrintWindow(printWindow, markup) {
  printWindow.document.open();
  printWindow.document.write(markup);
  printWindow.document.close();
}

export async function extractPdfRequestErrorMessage(requestError, fallbackMessage) {
  const responseData = requestError?.response?.data;

  if (responseData instanceof Blob) {
    try {
      const rawText = await responseData.text();
      const text = rawText.trim();
      if (text) {
        try {
          const parsed = JSON.parse(text);
          const messages = flattenErrors(parsed);
          if (messages[0]) {
            return messages[0];
          }
        } catch {
          return fallbackMessage;
        }
      }
    } catch {
      return fallbackMessage;
    }
  }

  const messages = flattenErrors(responseData);
  return messages[0] || fallbackMessage;
}

export async function startPdfPrintSession({ documentTitle, loadPdfBlob }) {
  const title = documentTitle || "طباعة ملف الوثيقة";
  const printWindow = window.open("", "_blank", "width=1100,height=820");

  if (!printWindow) {
    throw new Error("تعذر فتح نافذة الطباعة. يرجى السماح بالنوافذ المنبثقة لهذا الموقع ثم المحاولة مرة أخرى.");
  }

  let printUrl = "";
  let closeWatcherId = null;
  let cleaned = false;

  const cleanup = () => {
    if (cleaned) {
      return;
    }
    cleaned = true;
    if (closeWatcherId) {
      window.clearInterval(closeWatcherId);
      closeWatcherId = null;
    }
    if (printUrl) {
      URL.revokeObjectURL(printUrl);
      printUrl = "";
    }
  };

  const closeWindow = () => {
    cleanup();
    try {
      if (!printWindow.closed) {
        printWindow.close();
      }
    } catch {
      // Ignore browser-specific close failures.
    }
  };

  try {
    writePrintWindow(
      printWindow,
      renderPrintWindowMarkup({
        title,
        bodyContent: `
          <section class="loading-card">
            <h1>${escapeHtml(title)}</h1>
            <p>يتم تجهيز ملف PDF للطباعة الآن. ستظهر نافذة الطباعة تلقائيًا بعد اكتمال التحميل.</p>
          </section>
        `,
      })
    );

    const pdfBlob = await loadPdfBlob();
    printUrl = URL.createObjectURL(pdfBlob);

    closeWatcherId = window.setInterval(() => {
      if (printWindow.closed) {
        cleanup();
      }
    }, 750);

    writePrintWindow(
      printWindow,
      renderPrintWindowMarkup({
        title,
        bodyContent: `
          <section class="print-shell">
            <header class="print-header">
              <h1>${escapeHtml(title)}</h1>
              <p>هذه نافذة طباعة مستقرة لملف الوثيقة. إذا لم تفتح نافذة الطباعة تلقائيًا، استخدم زر "طباعة الآن".</p>
            </header>
            <main class="print-main">
              <section class="print-card">
                <div class="print-status">
                  <div>
                    <strong>جاهز للطباعة</strong>
                    <p id="print-status-text">يتم تجهيز عارض الملف. ستظهر نافذة الطباعة بعد لحظات.</p>
                  </div>
                  <div class="print-actions">
                    <button id="print-now-button" type="button" class="print-button print-button--primary">طباعة الآن</button>
                    <button id="close-window-button" type="button" class="print-button">إغلاق النافذة</button>
                  </div>
                </div>
                <iframe
                  id="pdf-print-frame"
                  class="print-frame"
                  title="${escapeHtml(title)}"
                  src="${escapeHtml(printUrl)}"
                ></iframe>
              </section>
            </main>
          </section>
          <script>
            (() => {
              const statusText = document.getElementById("print-status-text");
              const printButton = document.getElementById("print-now-button");
              const closeButton = document.getElementById("close-window-button");
              const frame = document.getElementById("pdf-print-frame");
              let hasTriggeredPrint = false;

              function tryPrint() {
                if (hasTriggeredPrint) {
                  return;
                }
                hasTriggeredPrint = true;
                statusText.textContent = "تم تجهيز الملف. يتم فتح نافذة الطباعة الآن.";
                window.setTimeout(() => {
                  try {
                    frame.contentWindow.focus();
                    frame.contentWindow.print();
                  } catch (error) {
                    try {
                      window.focus();
                      window.print();
                    } catch (printError) {
                      statusText.textContent = "تعذر فتح نافذة الطباعة تلقائيًا. يمكنك استخدام أمر الطباعة من المتصفح.";
                    }
                  }
                }, 400);
              }

              frame.addEventListener("load", () => {
                statusText.textContent = "تم تحميل ملف PDF بنجاح. ستظهر نافذة الطباعة الآن.";
                tryPrint();
              }, { once: true });

              printButton.addEventListener("click", () => {
                hasTriggeredPrint = false;
                tryPrint();
              });

              closeButton.addEventListener("click", () => {
                window.close();
              });

              window.addEventListener("afterprint", () => {
                statusText.textContent = "اكتملت محاولة الطباعة. يمكنك إغلاق هذه النافذة الآن.";
                window.setTimeout(() => {
                  window.close();
                }, 700);
              });

              window.setTimeout(() => {
                if (!hasTriggeredPrint) {
                  statusText.textContent = "إذا لم تظهر نافذة الطباعة تلقائيًا، اضغط زر 'طباعة الآن'.";
                }
              }, 2200);
            })();
          </script>
        `,
      })
    );

    return { cleanup, closeWindow };
  } catch (error) {
    writePrintWindow(
      printWindow,
      renderPrintWindowMarkup({
        title,
        accentColor: "#b42318",
        bodyContent: `
          <section class="error-card">
            <h1>${escapeHtml(title)}</h1>
            <p>تعذر تجهيز ملف PDF للطباعة. يمكنك إغلاق هذه النافذة ثم المحاولة مرة أخرى.</p>
          </section>
        `,
      })
    );
    window.setTimeout(closeWindow, 1800);
    throw error;
  }
}
