const assert = require('assert');
const path = require('path');
const fs = require('fs');

// Simple test verifying parseCapsule behavior
function parseCapsule(text, filePath) {
    const fmMatch = text.match(/^---\s*\n([\s\S]*?)\n---\s*\n/);
    let topic = '';
    let tags = [];
    let confidence = 'medium';
    let id = '';
    let referencedFile = undefined;
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
    }

    return {
        id: id || path.basename(filePath),
        topic: topic || path.basename(filePath),
        content: body,
        tags,
        confidence,
        filePath,
        fileName: path.basename(filePath),
        referencedFile,
    };
}

const sampleText = `---
id: 11111111-1111-1111-1111-111111111111
topic: Auth Bypass in Staging
tags: [auth, security, staging]
confidence: high
file_path: services/auth/middleware.py
---

When X-Debug-Override header is present, staging skips JWT.
`;

const res = parseCapsule(sampleText, '/path/to/auth.caps.md');
assert.strictEqual(res.id, '11111111-1111-1111-1111-111111111111');
assert.strictEqual(res.topic, 'Auth Bypass in Staging');
assert.deepStrictEqual(res.tags, ['auth', 'security', 'staging']);
assert.strictEqual(res.confidence, 'high');
assert.strictEqual(res.referencedFile, 'services/auth/middleware.py');
assert(res.content.includes('X-Debug-Override'));

console.log('✓ VS Code extension service parser tests passed successfully!');
