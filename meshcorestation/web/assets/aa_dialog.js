/* Run once while constructing dynamic dialogs, before their controls are bound. */
window.meshcorestationPrepareDialog = function (dialog) {
    if (dialog.querySelector(':scope > .dialog-body')) return;
    const header = dialog.querySelector(':scope > .dialog-header');
    if (!header) throw new Error('MeshcoreStation dialog requires a header');
    const body = document.createElement('div'); body.className = 'dialog-body';
    while (header.nextSibling) body.append(header.nextSibling);
    dialog.append(body);
};
