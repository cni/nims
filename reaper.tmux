#!/bin/bash
SESSION="REAPER"

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
cd nims
tmux new-session -s "$SESSION" -n bash -d

# processor
tmux new-window -t "$SESSION:1" -n "processor"
tmux send-keys -t "$SESSION:1" \
    "source ~/tg2env/bin/activate" C-m
tmux send-keys -t "$SESSION:1" \
    "nimsproc/processor.py -j8 -t /scratch_spinning -e \"~Epoch.psd.contains(u'mux')\" ${POSTGRES} ${NIMS_PATH} ${PHYSIO_PATH}" C-m

# mux processor
tmux new-window -t "$SESSION:2" -n "mux_proc"
tmux send-keys -t "$SESSION:2" \
    ". ~/tg2env/bin/activate" C-m
tmux send-keys -t "$SESSION:2" \
    "nimsproc/processor.py -j1 -k32 -t /scratch_spinning -e \"Epoch.psd.contains(u'mux')\" ${POSTGRES} ${NIMS_PATH} ${PHYSIO_PATH}" C-m

# QA
tmux new-window -t "$SESSION:3" -n "qa"
tmux send-keys -t "$SESSION:3" \
    ". ~/tg2env/bin/activate" C-m
tmux send-keys -t "$SESSION:3" \
    "nimsproc/qa_report.py -j8 ${POSTGRES} ${NIMS_PATH}" C-m

# attach to session
tmux select-window -t "$SESSION:0"
tmux attach-session -t "$SESSION"
