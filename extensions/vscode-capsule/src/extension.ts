import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { CapsuleService } from './capsuleService';
import { CapsuleHoverProvider } from './hoverProvider';
import { CapsuleTreeProvider } from './treeProvider';

export async function activate(context: vscode.ExtensionContext): Promise<void> {
    const service = new CapsuleService();
    const treeProvider = new CapsuleTreeProvider(service);
    const hoverProvider = new CapsuleHoverProvider(service);

    // Initial scan
    await service.initialize();

    // Register Hover Provider for all file documents
    context.subscriptions.push(
        vscode.languages.registerHoverProvider({ scheme: 'file' }, hoverProvider)
    );

    // Register TreeDataProvider
    context.subscriptions.push(
        vscode.window.registerTreeDataProvider('capsule-explorer', treeProvider)
    );

    // Status Bar Item
    const statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.command = 'capsule.search';
    const updateStatusBar = () => {
        const count = service.getAllCapsules().length;
        statusBarItem.text = `$(shield) Capsule (${count})`;
        statusBarItem.tooltip = `Capsule Memory: ${count} atomic capsules indexed`;
        statusBarItem.show();
    };
    updateStatusBar();
    context.subscriptions.push(statusBarItem);

    // Command: capsule.search
    context.subscriptions.push(
        vscode.commands.registerCommand('capsule.search', async () => {
            const capsules = service.getAllCapsules();
            if (capsules.length === 0) {
                vscode.window.showInformationMessage('No capsules found in workspace.');
                return;
            }

            const items: (vscode.QuickPickItem & { filePath: string })[] = capsules.map((c) => ({
                label: `$(shield) ${c.topic}`,
                description: `[${c.confidence}] ${c.tags.join(', ')}`,
                detail: c.content.substring(0, 100),
                filePath: c.filePath,
            }));

            const picked = await vscode.window.showQuickPick(items, {
                placeHolder: 'Search Capsule Memory Vault...',
                matchOnDescription: true,
                matchOnDetail: true,
            });

            if (picked) {
                const doc = await vscode.workspace.openTextDocument(picked.filePath);
                await vscode.window.showTextDocument(doc);
            }
        })
    );

    // Command: capsule.openCapsule
    context.subscriptions.push(
        vscode.commands.registerCommand('capsule.openCapsule', async (filePath: string) => {
            if (filePath && fs.existsSync(filePath)) {
                const doc = await vscode.workspace.openTextDocument(filePath);
                await vscode.window.showTextDocument(doc);
            }
        })
    );

    // Command: capsule.refreshTree
    context.subscriptions.push(
        vscode.commands.registerCommand('capsule.refreshTree', async () => {
            await service.reload();
            treeProvider.refresh();
            updateStatusBar();
        })
    );

    // Command: capsule.reconcile
    context.subscriptions.push(
        vscode.commands.registerCommand('capsule.reconcile', async () => {
            await service.reload();
            treeProvider.refresh();
            updateStatusBar();
            vscode.window.showInformationMessage('Capsule vault reconciled and cache refreshed.');
        })
    );

    // Command: capsule.new
    context.subscriptions.push(
        vscode.commands.registerCommand('capsule.new', async () => {
            const workspaceFolders = vscode.workspace.workspaceFolders;
            if (!workspaceFolders) {
                vscode.window.showErrorMessage('Please open a workspace folder to create capsules.');
                return;
            }

            const topic = await vscode.window.showInputBox({
                prompt: 'Enter capsule topic / invariant summary',
                placeHolder: 'e.g. Staging Auth Header Override',
            });
            if (!topic) {
                return;
            }

            const tagsRaw = await vscode.window.showInputBox({
                prompt: 'Enter comma-separated tags',
                placeHolder: 'e.g. auth, security, staging',
            });
            const tags = (tagsRaw || '')
                .split(',')
                .map((t) => t.trim())
                .filter((t) => t.length > 0);

            const confidence = await vscode.window.showQuickPick(['high', 'medium', 'low'], {
                placeHolder: 'Select confidence level',
            });
            if (!confidence) {
                return;
            }

            const config = vscode.workspace.getConfiguration('capsule');
            const targetDirName = config.get<string>('capsulesDirectory', 'caps');
            const targetDir = path.join(workspaceFolders[0].uri.fsPath, targetDirName);

            if (!fs.existsSync(targetDir)) {
                await fs.promises.mkdir(targetDir, { recursive: true });
            }

            const slug = topic
                .toLowerCase()
                .replace(/[^a-z0-9]+/g, '-')
                .replace(/^-|-$/g, '')
                .substring(0, 40);

            const fileName = `${slug}.caps.md`;
            const filePath = path.join(targetDir, fileName);

            const uuid = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
                const r = (Math.random() * 16) | 0;
                const v = c === 'x' ? r : (r & 0x3) | 0x8;
                return v.toString(16);
            });

            const template = `---
id: ${uuid}
topic: ${topic}
tags: [${tags.join(', ')}]
confidence: ${confidence}
---

Write your atomic invariant or technical knowledge here.
`;

            await fs.promises.writeFile(filePath, template, 'utf-8');
            await service.indexFile(filePath);
            treeProvider.refresh();
            updateStatusBar();

            const doc = await vscode.workspace.openTextDocument(filePath);
            await vscode.window.showTextDocument(doc);
        })
    );

    context.subscriptions.push({
        dispose: () => service.dispose(),
    });
}

export function deactivate(): void {}
