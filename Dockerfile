FROM quay.io/operator-framework/ansible-operator:v1.8.0
ARG worker_img=quay.io/redhat-performance/cluster-impairment-worker:latest

COPY requirements.yml ${HOME}/requirements.yml
RUN ansible-galaxy collection install -r ${HOME}/requirements.yml \
 && chmod -R ug+rwx ${HOME}/.ansible

COPY watches.yaml ${HOME}/watches.yaml
COPY roles/ ${HOME}/roles/
COPY playbooks/ ${HOME}/playbooks/
ENV WORKER_IMG ${worker_img}
