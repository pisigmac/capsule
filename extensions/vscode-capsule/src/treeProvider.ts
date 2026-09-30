import * as vscode from 'vscode';
import { CapsuleItem, CapsuleService } from './capsuleService';

export class CapsuleTreeItem extends vscode.TreeItem {
    constructor(
        public readonly label: string,
        public readonly collapsibleState: vscode.TreeItemCollapsibleState,
        public readonly capsule?: CapsuleItem,
        public readonly category?: string
    ) {
        super(label, collapsibleState);

        if (capsule) {
            this.description = capsule.tags.length > 0 ? `[${capsule.tags.slice(0, 2).join(', ')}]` : '';
            this.tooltip = new vscode.MarkdownString(
                `**${capsule.topic}**\n\n*Confidence: ${capsule.confidence}*\n\n${capsule.content.substring(0, 150)}...`
            );

            if (capsule.confidence === 'high') {
                this.iconPath = new vscode.ThemeIcon('shield', new vscode.ThemeColor('charts.green'));
            } else if (capsule.confidence === 'medium') {
                this.iconPath = new vscode.ThemeIcon('bookmark', new vscode.ThemeColor('charts.blue'));
            } else {
                this.iconPath = new vscode.ThemeIcon('note', new vscode.ThemeColor('charts.yellow'));
            }

            this.command = {
                command: 'capsule.openCapsule',
                title: 'Open Capsule',
                arguments: [capsule.filePath],
            };
            this.contextValue = 'capsuleItem';
        } else if (category) {
            this.iconPath = new vscode.ThemeIcon('folder');
            this.contextValue = 'categoryItem';
        }
    }
}

export class CapsuleTreeProvider implements vscode.TreeDataProvider<CapsuleTreeItem> {
    private _onDidChangeTreeData: vscode.EventEmitter<CapsuleTreeItem | undefined | void> = new vscode.EventEmitter<
        CapsuleTreeItem | undefined | void
    >();
    readonly onDidChangeTreeData: vscode.Event<CapsuleTreeItem | undefined | void> = this._onDidChangeTreeData.event;

    constructor(private service: CapsuleService) {}

    public refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    public getTreeItem(element: CapsuleTreeItem): vscode.TreeItem {
        return element;
    }

    public async getChildren(element?: CapsuleTreeItem): Promise<CapsuleTreeItem[]> {
        const capsules = this.service.getAllCapsules();

        if (!element) {
            // Root categories: High Confidence, Other Capsules, Tags
            const highConf = capsules.filter((c) => c.confidence === 'high');
            const otherConf = capsules.filter((c) => c.confidence !== 'high');

            const items: CapsuleTreeItem[] = [];
            if (highConf.length > 0) {
                items.push(
                    new CapsuleTreeItem(
                        `Architectural Invariants (${highConf.length})`,
                        vscode.TreeItemCollapsibleState.Expanded,
                        undefined,
                        'high'
                    )
                );
            }
            if (otherConf.length > 0) {
                items.push(
                    new CapsuleTreeItem(
                        `Knowledge Vault (${otherConf.length})`,
                        vscode.TreeItemCollapsibleState.Expanded,
                        undefined,
                        'other'
                    )
                );
            }

            if (items.length === 0) {
                return [new CapsuleTreeItem('No capsules indexed yet', vscode.TreeItemCollapsibleState.None)];
            }

            return items;
        }

        if (element.category === 'high') {
            return capsules
                .filter((c) => c.confidence === 'high')
                .map((c) => new CapsuleTreeItem(c.topic, vscode.TreeItemCollapsibleState.None, c));
        }

        if (element.category === 'other') {
            return capsules
                .filter((c) => c.confidence !== 'high')
                .map((c) => new CapsuleTreeItem(c.topic, vscode.TreeItemCollapsibleState.None, c));
        }

        return [];
    }
}
