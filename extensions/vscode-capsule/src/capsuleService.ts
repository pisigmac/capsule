import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';

export interface CapsuleItem {
    id: string;
    topic: string;
    content: string;
    tags: string[];
    confidence: string;
    filePath: string;
    fileName: string;
    referencedFile?: string;
    source?: string;
}

export class CapsuleService {
    private cache: Map<string, CapsuleItem> = new Map();
    private watcher?: vscode.FileSystemWatcher;

    constructor() {
        this.setupWatcher();
    }

    public async initialize(): Promise<void> {
        await this.reload();
    }

    public dispose(): void {
        this.watcher?.dispose();
    }

    public getAllCapsules(): CapsuleItem[] {
        return Array.from(this.cache.values());
    }

    public async reload(): Promise<void> {
        this.cache.clear();
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (!workspaceFolders) {
            return;
        }

        for (const folder of workspaceFolders) {
            await this.scanDirectory(folder.uri.fsPath);
        }
    }

    private setupWatcher(): void {
        this.watcher = vscode.workspace.createFileSystemWatcher('**/*.{caps.md,capsule.md,md}');

        this.watcher.onDidCreate(async (uri) => {
            await this.indexFile(uri.fsPath);
        });

        this.watcher.onDidChange(async (uri) => {
            await this.indexFile(uri.fsPath);
        });

        this.watcher.onDidDelete((uri) => {
            this.cache.delete(uri.fsPath);
        });
    }

    private async scanDirectory(dirPath: string): Promise<void> {
        if (!fs.existsSync(dirPath)) {
            return;
        }

        try {
            const entries = await fs.promises.readdir(dirPath, { withFileTypes: true });
            for (const entry of entries) {
                const fullPath = path.join(dirPath, entry.name);
                if (entry.name.startsWith('.') || entry.name === 'node_modules') {
                    continue;
                }

                if (entry.isDirectory()) {
                    await this.scanDirectory(fullPath);
                } else if (entry.isFile() && (entry.name.endsWith('.caps.md') || entry.name.endsWith('.capsule.md'))) {
                    await this.indexFile(fullPath);
                }
            }
        } catch (e) {
            console.error(`Error scanning directory ${dirPath}:`, e);
        }
    }

    public async indexFile(filePath: string): Promise<void> {
        if (!fs.existsSync(filePath)) {
            this.cache.delete(filePath);
            return;
        }

        try {
            const content = await fs.promises.readFile(filePath, 'utf-8');
            const item = this.parseCapsule(content, filePath);
            if (item) {
                this.cache.set(filePath, item);
            }
        } catch (e) {
            console.error(`Failed to index capsule ${filePath}:`, e);
        }
    }

    public parseCapsule(text: string, filePath: string): CapsuleItem | null {
        const fmMatch = text.match(/^---\s*\n([\s\S]*?)\n---\s*\n/);
        let topic = '';
        let tags: string[] = [];
        let confidence = 'medium';
        let id = '';
        let referencedFile: string | undefined = undefined;
        let source: string | undefined = undefined;
        let body = text;

        if (fmMatch) {
            const fmText = fmMatch[1];
            body = text.substring(fmMatch[0].length).trim();

            const topicMatch = fmText.match(/^topic:\s*(.+)$/m);
            if (topicMatch) {
                topic = topicMatch[1].trim().replace(/^["']|["']$/g, '');
            }

            const idMatch = fmText.match(/^id:\s*(.+)$/m);
            if (idMatch) {
                id = idMatch[1].trim();
            }

            const confMatch = fmText.match(/^confidence:\s*(.+)$/m);
            if (confMatch) {
                confidence = confMatch[1].trim().toLowerCase();
            }

            const sourceMatch = fmText.match(/^source:\s*(.+)$/m);
            if (sourceMatch) {
                source = sourceMatch[1].trim();
            }

            const fileRefMatch = fmText.match(/^file_path:\s*(.+)$/m);
            if (fileRefMatch) {
                referencedFile = fileRefMatch[1].trim().replace(/^["']|["']$/g, '');
            }

            const tagsMatch = fmText.match(/^tags:\s*\[(.*?)\]/m);
            if (tagsMatch) {
                tags = tagsMatch[1]
                    .split(',')
                    .map((t) => t.trim().replace(/^["']|["']$/g, ''))
                    .filter((t) => t.length > 0);
            }
        } else {
            const h1Match = text.match(/^#\s+(.+)$/m);
            if (h1Match) {
                topic = h1Match[1].trim();
            } else {
                topic = text.split('\n')[0].substring(0, 80);
            }
        }

        if (!topic && !body) {
            return null;
        }

        return {
            id: id || path.basename(filePath),
            topic: topic || path.basename(filePath, path.extname(filePath)),
            content: body,
            tags,
            confidence,
            filePath,
            fileName: path.basename(filePath),
            referencedFile,
            source,
        };
    }

    public search(query: string, limit: number = 10): CapsuleItem[] {
        const q = query.toLowerCase().trim();
        if (!q) {
            return Array.from(this.cache.values()).slice(0, limit);
        }

        const scored: { item: CapsuleItem; score: number }[] = [];
        for (const item of this.cache.values()) {
            let score = 0;
            if (item.topic.toLowerCase().includes(q)) {
                score += 10;
            }
            if (item.tags.some((t) => t.toLowerCase().includes(q))) {
                score += 5;
            }
            if (item.content.toLowerCase().includes(q)) {
                score += 2;
            }
            if (score > 0) {
                scored.push({ item, score });
            }
        }

        return scored
            .sort((a, b) => b.score - a.score)
            .slice(0, limit)
            .map((s) => s.item);
    }

    public findMatchingCapsules(document: vscode.TextDocument, position: vscode.Position): CapsuleItem[] {
        const wordRange = document.getWordRangeAtPosition(position);
        const word = wordRange ? document.getText(wordRange).toLowerCase() : '';
        const lineText = document.lineAt(position.line).text;
        const currentFilePath = vscode.workspace.asRelativePath(document.uri);
        const fileName = path.basename(currentFilePath).toLowerCase();
        const fileStem = path.basename(currentFilePath, path.extname(currentFilePath)).toLowerCase();

        const matches: CapsuleItem[] = [];

        for (const cap of this.cache.values()) {
            // 1. Direct explicit file reference match
            if (cap.referencedFile && (currentFilePath.includes(cap.referencedFile) || cap.referencedFile.includes(currentFilePath))) {
                matches.push(cap);
                continue;
            }

            // 2. Direct ID annotation match on current line (e.g. @capsule(id))
            if (cap.id && lineText.includes(cap.id)) {
                matches.push(cap);
                continue;
            }

            // 3. Hovered word matches capsule tag or topic
            if (word && word.length >= 3) {
                if (cap.tags.some((t) => t.toLowerCase() === word)) {
                    matches.push(cap);
                    continue;
                }
                if (cap.topic.toLowerCase().includes(word)) {
                    matches.push(cap);
                    continue;
                }
            }

            // 4. File stem matches tag
            if (cap.tags.some((t) => t.toLowerCase() === fileStem || t.toLowerCase() === fileName)) {
                matches.push(cap);
            }
        }

        return matches;
    }
}
