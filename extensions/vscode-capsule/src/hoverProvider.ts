import * as vscode from 'vscode';
import { CapsuleItem, CapsuleService } from './capsuleService';

export class CapsuleHoverProvider implements vscode.HoverProvider {
    constructor(private service: CapsuleService) {}

    public provideHover(
        document: vscode.TextDocument,
        position: vscode.Position,
        _token: vscode.CancellationToken
    ): vscode.ProviderResult<vscode.Hover> {
        const config = vscode.workspace.getConfiguration('capsule');
        if (!config.get<boolean>('enableHover', true)) {
            return null;
        }

        const confidenceFilter = config.get<string>('confidenceThreshold', 'all');
        const matches = this.service.findMatchingCapsules(document, position);
        if (!matches || matches.length === 0) {
            return null;
        }

        const filtered = matches.filter((cap) => {
            if (confidenceFilter === 'high') {
                return cap.confidence === 'high';
            }
            if (confidenceFilter === 'medium') {
                return cap.confidence === 'high' || cap.confidence === 'medium';
            }
            return true;
        });

        if (filtered.length === 0) {
            return null;
        }

        const md = new vscode.MarkdownString();
        md.isTrusted = true;
        md.supportHtml = true;

        // Display top 1-2 matching capsules
        const displayItems = filtered.slice(0, 2);
        for (let i = 0; i < displayItems.length; i++) {
            const cap = displayItems[i];
            this.formatCapsuleHover(md, cap);
            if (i < displayItems.length - 1) {
                md.appendMarkdown('\n\n---\n\n');
            }
        }

        return new vscode.Hover(md);
    }

    private formatCapsuleHover(md: vscode.MarkdownString, cap: CapsuleItem): void {
        const confidenceBadge =
            cap.confidence === 'high'
                ? '🟢 **High Confidence**'
                : cap.confidence === 'medium'
                ? '🔵 **Medium Confidence**'
                : '🟡 **Low Confidence**';

        md.appendMarkdown(`### 🛡️ Capsule Invariant: ${cap.topic}\n\n`);
        md.appendMarkdown(`${confidenceBadge}`);

        if (cap.tags && cap.tags.length > 0) {
            md.appendMarkdown(` | Tags: \`${cap.tags.join('`, `')}\``);
        }
        md.appendMarkdown('\n\n');

        // Excerpt body
        const cleanContent = cap.content.replace(/\r\n/g, '\n').trim();
        const excerpt = cleanContent.length > 250 ? cleanContent.substring(0, 250) + '...' : cleanContent;
        md.appendMarkdown(`> ${excerpt.replace(/\n/g, '\n> ')}\n\n`);

        // Command URI to open capsule file
        const openArgs = encodeURIComponent(JSON.stringify([cap.filePath]));
        md.appendMarkdown(`[📄 Open Capsule File](command:capsule.openCapsule?${openArgs})`);
    }
}
