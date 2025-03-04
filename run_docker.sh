# module_ids_we_are_considering=(1 12 14 22 24 25 27 28 29 30 31 37)
module_ids_we_are_considering=(12)
# module_ids_we_are_considering=(1 12 14 22 25 27 28 29 30 31 37)


for i in {1..40}
do
    if [[ ! " ${module_ids_we_are_considering[@]} " =~ " $i " ]]; then
        continue
    fi

    # remove the container otog-container_$i if it exists
    docker stop otog-container_$i
    docker rm otog-container_$i

    docker build -t dockerized-otog /home/tbaral/research/otog_icse/docker_project_template
    docker run --name otog-container_$i --memory=8g --memory-swap=8g -e ID=$i dockerized-otog

    mkdir -p /home/tbaral/research/otog_icse/results/$i

    # docker start otog-container_$i

    docker cp otog-container_$i:/app/dataset /home/tbaral/research/otog_icse/results/$i/
    docker cp otog-container_$i:/app/test_list /home/tbaral/research/otog_icse/results/$i/
    docker cp otog-container_$i:/app/runs_n25 /home/tbaral/research/otog_icse/results/$i/
    docker cp otog-container_$i:/app/random_test_orders_n25 /home/tbaral/research/otog_icse/results/$i/

    # docker stop otog-container_$i
    # docker rm otog-container_$i
done