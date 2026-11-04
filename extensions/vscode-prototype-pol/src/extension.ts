import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { exec } from 'child_process';

let outputChannel: vscode.OutputChannel;

export function activate(context: vscode.ExtensionContext) {
    outputChannel = vscode.window.createOutputChannel("Prototype.pol");
    context.subscriptions.push(outputChannel);

    outputChannel.appendLine("[Prototype.pol] Extension activated successfully.");

    // Command: Compile Current File
    const compileCommand = vscode.commands.registerCommand('prototype.compileCurrentFile', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showWarningMessage("No active editor found. Open a .pol or .pollib file to compile.");
            return;
        }

        const document = editor.document;
        const filePath = document.fileName;
        const ext = path.extname(filePath).toLowerCase();

        if (ext !== '.pol' && ext !== '.pollib') {
            vscode.window.showWarningMessage(`Active file '${path.basename(filePath)}' is not a Prototype.pol (.pol / .pollib) source file.`);
            return;
        }

        // Auto-save if dirty
        if (document.isDirty) {
            await document.save();
        }

        // Resolve compiler path
        const config = vscode.workspace.getConfiguration('prototype');
        let compilerPath = config.get<string>('compilerPath');

        // Look for workspace polc.py if compilerPath is not explicitly configured
        if (!compilerPath && vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders.length > 0) {
            const root = vscode.workspace.workspaceFolders[0].uri.fsPath;
            const candidate = path.join(root, 'polc.py');
            if (fs.existsSync(candidate)) {
                compilerPath = candidate;
            }
        }

        if (!compilerPath || !fs.existsSync(compilerPath)) {
            const message = "Prototype.pol compiler interface has not yet been configured for this environment. " +
                "To enable compilation, please configure 'prototype.compilerPath' in Settings or place 'polc.py' in the workspace root.";
            outputChannel.appendLine(`[CONFIG REQUIRED] ${message}`);
            outputChannel.show(true);
            vscode.window.showInformationMessage(message, "Open Settings").then(selection => {
                if (selection === "Open Settings") {
                    vscode.commands.executeCommand('workbench.action.openSettings', 'prototype.compilerPath');
                }
            });
            return;
        }

        // Determine destination output JSON
        const outputDir = config.get<string>('outputDirectory') || 'topology_src';
        const baseName = path.basename(filePath, ext);
        const workspaceRoot = (vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0])
            ? vscode.workspace.workspaceFolders[0].uri.fsPath
            : path.dirname(filePath);
        const resolvedOutDir = path.isAbsolute(outputDir) ? outputDir : path.join(workspaceRoot, outputDir);
        const outJson = path.join(resolvedOutDir, `${baseName}.json`);

        const cmd = `py -3 "${compilerPath}" "${filePath}" -o "${outJson}"`;
        outputChannel.appendLine(`[COMPILE] Running: ${cmd}`);
        outputChannel.show(true);

        exec(cmd, { cwd: workspaceRoot }, (error, stdout, stderr) => {
            if (stdout) {
                outputChannel.appendLine(stdout.trim());
            }
            if (stderr) {
                outputChannel.appendLine(`[STDERR] ${stderr.trim()}`);
            }

            if (error) {
                vscode.window.showErrorMessage(`Prototype.pol compilation failed: ${error.message}`);
                outputChannel.appendLine(`[ERROR] Compilation failed with code ${error.code}`);
            } else {
                vscode.window.showInformationMessage(
                    `Successfully compiled ${path.basename(filePath)} -> ${path.basename(outJson)}`,
                    "Open JSON"
                ).then(sel => {
                    if (sel === "Open JSON" && fs.existsSync(outJson)) {
                        vscode.workspace.openTextDocument(outJson).then(doc => vscode.window.showTextDocument(doc));
                    }
                });
            }
        });
    });

    // Command: Check Current File
    const checkCommand = vscode.commands.registerCommand('prototype.checkCurrentFile', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showWarningMessage("No active editor found. Open a .pol or .pollib file to check.");
            return;
        }

        const document = editor.document;
        const filePath = document.fileName;
        const ext = path.extname(filePath).toLowerCase();

        if (ext !== '.pol' && ext !== '.pollib') {
            vscode.window.showWarningMessage(`Active file '${path.basename(filePath)}' is not a Prototype.pol source file.`);
            return;
        }

        // Check if compiler is available for dry-run validation
        const config = vscode.workspace.getConfiguration('prototype');
        let compilerPath = config.get<string>('compilerPath');
        if (!compilerPath && vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders.length > 0) {
            const root = vscode.workspace.workspaceFolders[0].uri.fsPath;
            const candidate = path.join(root, 'polc.py');
            if (fs.existsSync(candidate)) {
                compilerPath = candidate;
            }
        }

        if (!compilerPath || !fs.existsSync(compilerPath)) {
            const message = "Prototype.pol syntax verification has not yet been configured. " +
                "Configure 'prototype.compilerPath' in Settings to enable automated file checking.";
            outputChannel.appendLine(`[INFO] ${message}`);
            vscode.window.showInformationMessage(message);
            return;
        }

        const workspaceRoot = (vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0])
            ? vscode.workspace.workspaceFolders[0].uri.fsPath
            : path.dirname(filePath);

        outputChannel.appendLine(`[CHECK] Validating ${filePath}...`);
        outputChannel.show(true);

        const cmd = `py -3 "${compilerPath}" "${filePath}"`;
        exec(cmd, { cwd: workspaceRoot }, (error, stdout, stderr) => {
            if (stdout) {
                outputChannel.appendLine(stdout.trim());
            }
            if (stderr) {
                outputChannel.appendLine(`[STDERR] ${stderr.trim()}`);
            }

            if (error) {
                vscode.window.showErrorMessage(`Validation failed for ${path.basename(filePath)}.`);
            } else {
                vscode.window.showInformationMessage(`Validation passed: '${path.basename(filePath)}' is syntactically valid.`);
            }
        });
    });

    context.subscriptions.push(compileCommand);
    context.subscriptions.push(checkCommand);
}

export function deactivate() {
    if (outputChannel) {
        outputChannel.dispose();
    }
}
