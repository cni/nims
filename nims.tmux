#!/bin/bash
SESSION="CNI-NIMS"

POSTGRES_USER="nims"
POSTGRES_PW="nims"
POSTGRES_HOST="cnifs.stanford.edu"
POSTGRES_PORT="5432"
POSTGRES_DB="nims"
POSTGRES="postgresql://${POSTGRES_USER}:${POSTGRES_PW}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"

UNSORTABLE_PATH="/scratch/cni/unsortable"   # where to place unsortable files
STAGE_PATH="/scratch/cni/upload"            # where uploads are placed, where sorter looks for new files
NIMS_PATH="/cnifs/nims"                     # base path where files get sorted
PHYSIO_PATH="/cnifs/nims/physio"            # where physio files are unpacked into

# create
cd /var/local/nims
tmux new-session -s "$SESSION" -n bash -d

# sorter
tmux new-window -t "$SESSION:1" -n "sorter"
tmux send-keys -t "$SESSION:1" \
    "source /var/local/tg2env/bin/activate" C-m
tmux send-keys -t "$SESSION:1" \
    "PYTHONPATH=. nimsproc/sorter.py -p ${UNSORTABLE_PATH} ${POSTGRES} ${STAGE_PATH} ${NIMS_PATH}" C-m

# scheduler
tmux new-window -t "$SESSION:2" -n "scheduler"
tmux send-keys -t "$SESSION:2" \
    "source /var/local/tg2env/bin/activate" C-m
tmux send-keys -t "$SESSION:2" \
    "PYTHONPATH=. nimsproc/scheduler.py ${POSTGRES} ${NIMS_PATH}" C-m

# attach to session
tmux select-window -t "$SESSION:0"
tmux attach-session -t "$SESSION"
