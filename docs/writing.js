// Copy buttons for the command and prompt blocks on writing.html.
// Without JavaScript the buttons stay hidden and every block remains selectable text.
// Nothing is sent anywhere: the text goes to the local clipboard only.
const status = document.getElementById('copy-status');

function announce(message) {
  if (status) status.textContent = message;
}

function legacyCopy(text) {
  const area = document.createElement('textarea');
  area.value = text;
  area.setAttribute('readonly', '');
  area.style.position = 'fixed';
  area.style.top = '-1000px';
  document.body.appendChild(area);
  area.select();
  let copied = false;
  try {
    copied = document.execCommand('copy');
  } catch (error) {
    copied = false;
  }
  area.remove();
  return copied;
}

async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (error) {
      // Permission denied or unavailable: fall back below.
    }
  }
  return legacyCopy(text);
}

function selectContents(node) {
  const range = document.createRange();
  range.selectNodeContents(node);
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
}

for (const button of document.querySelectorAll('button[data-copy]')) {
  const target = document.getElementById(button.dataset.copy);
  if (!target) continue;
  const label = button.textContent;
  let timer = 0;
  button.hidden = false;
  button.addEventListener('click', async () => {
    const text = target.textContent.replace(/\s+$/, '');
    const copied = await copyText(text);
    if (copied) {
      button.textContent = 'Copied';
      announce('Copied to the clipboard.');
    } else {
      selectContents(target);
      button.textContent = 'Selected';
      announce('Copying is unavailable here. The text is selected; press Control+C or Command+C.');
    }
    clearTimeout(timer);
    timer = setTimeout(() => { button.textContent = label; }, 2200);
  });
}
