
Based on everything you've told me, here's what I think would work best

Because you:

log into EMR every day,
have a separate Gateway,
perform lots of file operations,
use Spark,
and authenticate with MFA,

I would create a remote workspace on the EMR server.

Something like:

~/etl-workspace/

├── notebooks/
├── scala/
├── scripts/
│     setup_env.sh
│     move_files.sh
│     copy_gateway.sh
│     cleanup.sh
├── configs/
│     env.sh
└── README.md

Then use VS Code Remote - SSH to open ~/etl-workspace directly. From there:

Edit scripts with full IDE support.
Run them in the integrated terminal.
Develop ETL logic in notebooks or Scala files.
Use Git to version everything.

This way, you're no longer copying commands from Notepad—you have a real, maintainable development environment that lives where the work actually executes.
