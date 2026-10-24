import java.sql.*;
import java.nio.file.*;
public class DuckDbScripts {
 public static void main(String[] args) throws Exception {
  Class.forName("org.duckdb.DuckDBDriver");
  try(Connection c=DriverManager.getConnection("jdbc:duckdb:"+args[0]); Statement s=c.createStatement()) {
   for(int i=1;i<args.length;i++) s.execute(Files.readString(Path.of(args[i])));
  }
 }
}
