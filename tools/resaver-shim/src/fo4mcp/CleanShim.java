// CleanShim — headless ReSaver (Apache-2.0) wrapper for FO4 Papyrus-VM save cleaning.
//
// Removes undefined script elements / unattached instances from a .fos by driving
// ReSaver's battle-tested engine (resaver.ess.ESS + Papyrus), which we do NOT
// reimplement in Python. ESS.readESS builds only Swing models (no window), so it
// runs headless; ModelBuilder uses a non-daemon thread pool, hence the explicit
// System.exit() at the end.
//
//   java -cp "<jdkcp>" fo4mcp.CleanShim --in <fos> --out <fos> --op noop|undefined|unattached
//
// stdout: one JSON object with before/after stats (proves the output re-reads).
// exit 0 = ok, 2 = bad args / failure.
//
// Apache-2.0 (links ReSaver, Apache-2.0) — redistribution-safe, no GPL contagion.

package fo4mcp;

import java.nio.file.Paths;
import java.util.Set;
import resaver.ProgressModel;
import resaver.ess.ESS;
import resaver.ess.ModelBuilder;
import resaver.ess.papyrus.Papyrus;
import resaver.ess.papyrus.PapyrusElement;

public class CleanShim {

    public static void main(String[] argv) {
        String in = null, out = null, op = null;
        for (int i = 0; i + 1 < argv.length; i += 2) {
            switch (argv[i]) {
                case "--in":  in  = argv[i + 1]; break;
                case "--out": out = argv[i + 1]; break;
                case "--op":  op  = argv[i + 1]; break;
                default: fail("unknown arg: " + argv[i]);
            }
        }
        if (in == null || out == null || op == null)
            fail("usage: --in <fos> --out <fos> --op noop|undefined|unattached");
        if (!op.equals("noop") && !op.equals("undefined") && !op.equals("unattached"))
            fail("op must be noop|undefined|unattached");

        try {
            ESS before = ESS.readESS(Paths.get(in), new ModelBuilder(new ProgressModel())).ESS;
            String statsIn = stats(before);

            int removed = 0;
            Papyrus pap = before.getPapyrus();
            if (op.equals("undefined")) {
                Set<PapyrusElement> r = pap.removeUndefinedElements();
                removed = r.size();
            } else if (op.equals("unattached")) {
                Set<PapyrusElement> r = pap.removeUnattachedInstances();
                removed = r.size();
            }

            ESS.writeESS(before, Paths.get(out), false);

            // Re-read what we just wrote: the corruption-safety oracle. If the
            // output parses back through ReSaver's reader, the re-serialize is
            // structurally sound.
            ESS after = ESS.readESS(Paths.get(out), new ModelBuilder(new ProgressModel())).ESS;
            String statsOut = stats(after);

            System.out.println("{"
                + "\"ok\":true,\"op\":\"" + op + "\",\"removed_count\":" + removed
                + ",\"reread_ok\":true"
                + ",\"before\":" + statsIn
                + ",\"after\":" + statsOut
                + ",\"in\":" + jstr(in) + ",\"out\":" + jstr(out)
                + "}");
            System.out.flush();
            System.exit(0);
        } catch (Throwable t) {
            System.err.println("ERROR: " + t);
            t.printStackTrace();
            System.exit(2);
        }
    }

    // The Papyrus-VM tables that undefined/unattached removal touches, plus the
    // change-form + formID totals, so before/after deltas are visible.
    static String stats(ESS ess) {
        Papyrus p = ess.getPapyrus();
        return "{"
            + "\"changeforms\":" + ess.getChangeForms().size()
            + ",\"formids\":" + ess.getFormIDs().length
            + ",\"script_instances\":" + p.getScriptInstances().size()
            + ",\"references\":" + p.getReferences().size()
            + ",\"active_scripts\":" + p.getActiveScripts().size()
            + ",\"broken\":" + ess.isBroken()
            + "}";
    }

    static void fail(String m) { System.err.println(m); System.exit(2); }

    static String jstr(String s) {
        return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
    }
}
